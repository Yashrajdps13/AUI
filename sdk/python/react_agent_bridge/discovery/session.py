import asyncio
import logging
import time
from typing import Optional

from react_agent_bridge.discovery.corpus import ObservationCorpus
from react_agent_bridge.discovery.recorder import HumanSessionRecorder
from react_agent_bridge.discovery.analyzer.slot_annotator import SlotAnnotationEngine
from react_agent_bridge.discovery.analyzer.workflow import WorkflowInferenceEngine
from react_agent_bridge.discovery.analyzer.precondition import PreconditionInferenceEngine
from react_agent_bridge.discovery.analyzer.constraint import ConstraintInferenceEngine
from react_agent_bridge.discovery.generator.context_writer import ContextWriter

logger = logging.getLogger("react_agent_bridge.discovery.session")


class DiscoverySession:
    """
    Public entry point for the developer to run Discovery Mode,
    manage session recorders, and control background/on-demand context generation.
    """
    def __init__(
        self,
        bridge,
        output_path: str = "./agent-context.md",
        db_path: str = "./discovery.db",
        min_sessions: int = 3,
        inference_interval_hours: float = 24.0,
        min_confidence_for_workflow: float = 0.6,
        min_confidence_for_constraint: float = 0.7,
        golden_trace_min_confidence: float = 0.8
    ):
        self.bridge = bridge
        self.output_path = output_path
        self.db_path = db_path
        self.min_sessions = min_sessions
        self.inference_interval_hours = inference_interval_hours
        self.min_confidence_for_workflow = min_confidence_for_workflow
        self.min_confidence_for_constraint = min_confidence_for_constraint
        self.golden_trace_min_confidence = golden_trace_min_confidence

        self.corpus = ObservationCorpus(db_path)
        self.recorder: Optional[HumanSessionRecorder] = None
        self._bg_task: Optional[asyncio.Task] = None
        self._sessions_limit: Optional[int] = None
        self._sessions_recorded = 0

        # Store output path in settings
        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('output_path', ?)", (self.output_path,))
            conn.commit()
            conn.close()
        except Exception:
            pass

        self.annotator = SlotAnnotationEngine(self.corpus)
        self.wf_engine = WorkflowInferenceEngine(self.corpus)
        self.pre_engine = PreconditionInferenceEngine(self.corpus, min_pairs=1)
        self.constraint_engine = ConstraintInferenceEngine(self.corpus, min_sessions=self.min_sessions)

        # Register connection listeners on bridge
        self.bridge.add_listener("connect", self._on_connect)
        self.bridge.add_listener("disconnect", self._on_disconnect)

    def _on_connect(self):
        # Run in a future task since start is async
        asyncio.create_task(self._start_recorder())

    async def _start_recorder(self):
        logger.info("Starting new passive observation session...")
        self.recorder = HumanSessionRecorder(self.bridge, self.corpus, session_type="human")
        self.bridge._discovery_recorder = self.recorder
        await self.recorder.start()

    def _on_connect_agent(self):
        # We also support recording agent sessions
        asyncio.create_task(self._start_recorder_agent())

    async def _start_recorder_agent(self):
        logger.info("Recording active agent session...")
        self.recorder = HumanSessionRecorder(self.bridge, self.corpus, session_type="agent")
        self.bridge._discovery_recorder = self.recorder
        await self.recorder.start()

    def _on_disconnect(self):
        # Run in a task
        asyncio.create_task(self._stop_recorder())

    async def _stop_recorder(self):
        if self.recorder:
            logger.info("Connection closed. Finalizing passive session...")
            is_complete = False
            try:
                import sqlite3
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM events WHERE session_id = ?", (self.recorder.session_id,))
                cnt = cursor.fetchone()[0]
                conn.close()
                is_complete = cnt >= 5  # Lower threshold from 20 to 5 for developer testing
                logger.info(f"Session ended with {cnt} events. is_complete={is_complete}")
            except Exception as e:
                logger.error(f"Failed to check event count: {e}")

            await self.recorder.stop(is_complete=is_complete)
            self.recorder = None
            self.bridge._discovery_recorder = None

            self._sessions_recorded += 1
            if self._sessions_limit and self._sessions_recorded >= self._sessions_limit:
                logger.info(f"Recorded limit of {self._sessions_limit} sessions. Stopping bridge server...")
                await self.bridge.stop()

    async def run_until_interrupted(self):
        """
        Runs the bridge WebSocket server and keeps discovery mode active indefinitely.
        """
        # Ensure bridge server is started if not already
        if not self.bridge._server:
            await self.bridge.start()

        # Start background schedule
        self._start_bg_scheduler()

        try:
            while True:
                await asyncio.sleep(1.0)
        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("Discovery session interrupted. Stopping background processes.")
        finally:
            self._stop_bg_scheduler()

    async def run_for_sessions(self, n: int = 10):
        """
        Runs the discovery server until n completed sessions have been recorded.
        """
        self._sessions_limit = n
        self._sessions_recorded = 0

        if not self.bridge._server:
            await self.bridge.start()

        self._start_bg_scheduler()

        try:
            while self._sessions_recorded < n:
                await asyncio.sleep(1.0)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            self._stop_bg_scheduler()

    def _start_bg_scheduler(self):
        if self.inference_interval_hours > 0:
            self._bg_task = asyncio.create_task(self._scheduler_loop())
            logger.info(f"Started background discovery inference scheduler (every {self.inference_interval_hours}h).")

    def _stop_bg_scheduler(self):
        if self._bg_task:
            self._bg_task.cancel()
            self._bg_task = None

    async def _scheduler_loop(self):
        interval_secs = self.inference_interval_hours * 3600.0
        try:
            while True:
                await asyncio.sleep(interval_secs)
                logger.info("Scheduled background inference cycle executing...")
                await self.generate()
        except asyncio.CancelledError:
            pass

    async def generate(self):
        """
        Performs full/incremental analytical updates and writes/updates agent-context.md.
        """
        logger.info("Executing analytical inference cycle...")

        # 1. Run slot annotator engine
        annotations = await self.annotator.analyze()

        # 2. Run workflow inference engine
        workflows = await self.wf_engine.analyze(
            min_confidence=self.min_confidence_for_workflow,
            llm_adapter=self.bridge.llm_adapter
        )

        # 3. Run precondition engine
        preconditions = await self.pre_engine.analyze_preconditions(workflows)
        for wf in workflows:
            wf["preconditions"] = preconditions.get(wf["name"], [])

        # 4. Run constraint engine
        constraints = await self.constraint_engine.analyze(annotations)

        # 5. Compile session metrics
        sessions = await self.corpus.get_sessions()
        session_metrics = {
            "total": len(sessions),
            "human": sum(1 for s in sessions if s["session_type"] == "human"),
            "agent": sum(1 for s in sessions if s["session_type"] == "agent"),
            "interval_hours": self.inference_interval_hours
        }

        # 6. Retrieve current version hash from most recent session
        version_hash = "initial_v1"
        if sessions:
            version_hash = sessions[-1].get("application_version_hash", "initial_v1")

        # 7. Write output
        writer = ContextWriter(self.output_path)
        report_str = writer.write(
            annotations=annotations,
            workflows=workflows,
            inferred_constraints=constraints,
            session_metrics=session_metrics,
            version_hash=version_hash
        )

        # 8. Record inference run
        await self.corpus.record_inference_run(
            timestamp=time.time(),
            sessions_processed=len(sessions),
            changes_detected=len(workflows) + len(constraints)
        )

        class GenerationResult:
            def __init__(self, r_str):
                self.report = r_str

        return GenerationResult(report_str)
