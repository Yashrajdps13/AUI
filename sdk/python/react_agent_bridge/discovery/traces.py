import sqlite3
import json
import uuid
import time
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

logger = logging.getLogger("react_agent_bridge.discovery.traces")


@dataclass
class GoldenTraceStep:
    command_type: str  # setState, dispatchEvent, callAction, waitFor
    target: str
    value: Any = None
    event: Optional[str] = None
    selector: Optional[str] = None
    args: Optional[List[Any]] = None
    pre_state_snapshot: Dict[str, Any] = field(default_factory=dict)
    post_state_snapshot: Dict[str, Any] = field(default_factory=dict)
    settle_time_ms: float = 0.0


@dataclass
class GoldenTrace:
    trace_id: str
    workflow_name: str
    goal_description: str
    recorded_at: float
    application_version_hash: str
    precondition_state: Dict[str, Any]
    steps: List[GoldenTraceStep]
    postcondition_state: Dict[str, Any]
    execution_time_ms: float
    llm_calls_made: int
    confidence: float = 1.0


class GoldenTraceStore:
    """
    Manages SQLite storage for Golden Traces.
    """
    def __init__(self, db_path: str = "discovery.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS golden_traces (
                    trace_id TEXT PRIMARY KEY,
                    workflow_name TEXT NOT NULL,
                    goal_description TEXT NOT NULL,
                    recorded_at REAL NOT NULL,
                    application_version_hash TEXT NOT NULL,
                    precondition_state_json TEXT NOT NULL,
                    postcondition_state_json TEXT NOT NULL,
                    execution_time_ms REAL NOT NULL,
                    llm_calls_made INTEGER NOT NULL,
                    confidence REAL NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS golden_trace_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    command_type TEXT NOT NULL,
                    target TEXT NOT NULL,
                    value_json TEXT,
                    event TEXT,
                    selector TEXT,
                    args_json TEXT,
                    pre_state_snapshot_json TEXT NOT NULL,
                    post_state_snapshot_json TEXT NOT NULL,
                    settle_time_ms REAL NOT NULL,
                    FOREIGN KEY (trace_id) REFERENCES golden_traces(trace_id) ON DELETE CASCADE
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_traces_wf ON golden_traces(workflow_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trace_steps_id ON golden_trace_steps(trace_id)")
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize Golden Trace DB: {e}")
        finally:
            conn.close()

    def record_trace(self, trace: GoldenTrace):
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO golden_traces (
                    trace_id, workflow_name, goal_description, recorded_at,
                    application_version_hash, precondition_state_json, postcondition_state_json,
                    execution_time_ms, llm_calls_made, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trace.trace_id,
                trace.workflow_name,
                trace.goal_description,
                trace.recorded_at,
                trace.application_version_hash,
                json.dumps(trace.precondition_state),
                json.dumps(trace.postcondition_state),
                trace.execution_time_ms,
                trace.llm_calls_made,
                trace.confidence
            ))

            for idx, s in enumerate(trace.steps):
                cursor.execute("""
                    INSERT INTO golden_trace_steps (
                        trace_id, step_index, command_type, target, value_json,
                        event, selector, args_json, pre_state_snapshot_json,
                        post_state_snapshot_json, settle_time_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    trace.trace_id,
                    idx,
                    s.command_type,
                    s.target,
                    json.dumps(s.value) if s.value is not None else None,
                    s.event,
                    s.selector,
                    json.dumps(s.args) if s.args is not None else None,
                    json.dumps(s.pre_state_snapshot),
                    json.dumps(s.post_state_snapshot),
                    s.settle_time_ms
                ))
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to record golden trace: {e}")
        finally:
            conn.close()

    def _matches_precondition(self, pre_state: dict, current_state: dict) -> bool:
        """
        Validates if current state matches the precondition snapshot within tolerance.
        """
        for key, pre_val in pre_state.items():
            if key not in current_state:
                return False
            curr_val = current_state[key]

            # Numeric tolerance ±10%
            if isinstance(pre_val, (int, float)) and isinstance(curr_val, (int, float)):
                if pre_val == 0:
                    if curr_val != 0:
                        return False
                else:
                    diff_ratio = abs(curr_val - pre_val) / abs(pre_val)
                    if diff_ratio > 0.1:
                        return False
            else:
                # String, boolean or collections must match exactly
                if curr_val != pre_val:
                    return False
        return True

    def find_applicable_traces(self, workflow_name: str, current_state: dict, min_confidence: float = 0.8) -> List[GoldenTrace]:
        conn = sqlite3.connect(self.db_path)
        traces = []
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT trace_id, workflow_name, goal_description, recorded_at,
                       application_version_hash, precondition_state_json, postcondition_state_json,
                       execution_time_ms, llm_calls_made, confidence
                FROM golden_traces
                WHERE (workflow_name = ? OR goal_description = ?) AND confidence >= ?
                ORDER BY confidence DESC, recorded_at DESC
            """, (workflow_name, workflow_name, min_confidence))
            rows = cursor.fetchall()

            for r in rows:
                tid, wf, gd, rat, avh, pre_j, post_j, et, llm_c, conf = r
                pre_state = json.loads(pre_j)
                
                # Check precondition applicability
                if not self._matches_precondition(pre_state, current_state):
                    continue

                # Load steps
                cursor.execute("""
                    SELECT command_type, target, value_json, event, selector, args_json,
                           pre_state_snapshot_json, post_state_snapshot_json, settle_time_ms
                    FROM golden_trace_steps
                    WHERE trace_id = ?
                    ORDER BY step_index ASC
                """, (tid,))
                step_rows = cursor.fetchall()
                steps = []
                for sr in step_rows:
                    steps.append(GoldenTraceStep(
                        command_type=sr[0],
                        target=sr[1],
                        value=json.loads(sr[2]) if sr[2] else None,
                        event=sr[3],
                        selector=sr[4],
                        args=json.loads(sr[5]) if sr[5] else None,
                        pre_state_snapshot=json.loads(sr[6]),
                        post_state_snapshot=json.loads(sr[7]),
                        settle_time_ms=sr[8]
                    ))

                traces.append(GoldenTrace(
                    trace_id=tid,
                    workflow_name=wf,
                    goal_description=gd,
                    recorded_at=rat,
                    application_version_hash=avh,
                    precondition_state=pre_state,
                    steps=steps,
                    postcondition_state=json.loads(post_j),
                    execution_time_ms=et,
                    llm_calls_made=llm_c,
                    confidence=conf
                ))
        except Exception as e:
            logger.error(f"Failed to query applicable traces: {e}", exc_info=True)
        finally:
            conn.close()
        return traces

    def update_trace_confidence(self, trace_id: str, succeeded: bool):
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT confidence FROM golden_traces WHERE trace_id = ?", (trace_id,))
            row = cursor.fetchone()
            if not row:
                return

            conf = row[0]
            if succeeded:
                conf = min(1.0, conf * 1.05)
            else:
                conf = conf * 0.7

            if conf < 0.3:
                # Deprecate / remove trace
                cursor.execute("DELETE FROM golden_traces WHERE trace_id = ?", (trace_id,))
                cursor.execute("DELETE FROM golden_trace_steps WHERE trace_id = ?", (trace_id,))
            else:
                cursor.execute("UPDATE golden_traces SET confidence = ? WHERE trace_id = ?", (conf, trace_id))
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to update trace confidence: {e}")
        finally:
            conn.close()

    def deprecate_traces_for_version(self, old_version_hash: str):
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            # Mark traces of older application versions as deprecated (confidence = 0.0, or delete them)
            cursor.execute("DELETE FROM golden_traces WHERE application_version_hash = ?", (old_version_hash,))
            cursor.execute("""
                DELETE FROM golden_trace_steps 
                WHERE trace_id NOT IN (SELECT trace_id FROM golden_traces)
            """)
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to deprecate traces for old version: {e}")
        finally:
            conn.close()
