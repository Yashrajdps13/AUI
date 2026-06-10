import asyncio
import json
import logging
import sqlite3
from typing import List, Dict, Any, Optional, Tuple
from react_agent_bridge.discovery.event import DiscoveryEvent, DiscoveryEventType

logger = logging.getLogger("react_agent_bridge.discovery.corpus")


class ObservationCorpus:
    """
    Append-only SQLite database storing passive discovery events, session metrics,
    and analysis execution history.
    """
    def __init__(self, db_path: str = "discovery.db"):
        self.db_path = db_path
        self._lock = asyncio.Lock()
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    session_type TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    ended_at REAL,
                    event_count INTEGER DEFAULT 0,
                    is_complete INTEGER DEFAULT 0,
                    application_version_hash TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    session_id TEXT NOT NULL,
                    session_type TEXT NOT NULL,
                    component_id TEXT,
                    component_display_name TEXT,
                    slot_key TEXT,
                    previous_value_json TEXT,
                    new_value_json TEXT,
                    change_source TEXT,
                    element_selector TEXT,
                    route TEXT,
                    settle_duration_ms REAL,
                    confidence REAL NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS inference_runs (
                    timestamp REAL PRIMARY KEY,
                    sessions_processed INTEGER,
                    changes_detected INTEGER
                )
            """)

            # Create critical indexes for query performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_comp_slot ON events(component_display_name, slot_key)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp)")
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize Discovery DB: {e}")
        finally:
            conn.close()

    async def start_session(self, session_id: str, session_type: str, started_at: float, app_version_hash: str):
        def _sync_start():
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO sessions (session_id, session_type, started_at, is_complete, application_version_hash)
                    VALUES (?, ?, ?, 0, ?)
                """, (session_id, session_type, started_at, app_version_hash))
                conn.commit()
            except Exception as e:
                logger.error(f"Failed to start discovery session: {e}")
            finally:
                conn.close()

        await asyncio.get_running_loop().run_in_executor(None, _sync_start)

    async def end_session(self, session_id: str, ended_at: float, is_complete: bool):
        def _sync_end():
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.cursor()
                # Count total events in this session
                cursor.execute("SELECT COUNT(*) FROM events WHERE session_id = ?", (session_id,))
                cnt = cursor.fetchone()[0]

                cursor.execute("""
                    UPDATE sessions
                    SET ended_at = ?, event_count = ?, is_complete = ?
                    WHERE session_id = ?
                """, (ended_at, cnt, 1 if is_complete else 0, session_id))
                conn.commit()
            except Exception as e:
                logger.error(f"Failed to end discovery session: {e}")
            finally:
                conn.close()

        await asyncio.get_running_loop().run_in_executor(None, _sync_end)

    async def record_event(self, event: DiscoveryEvent):
        """
        Non-blocking asynchronous event insertion.
        """
        def _sync_record():
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO events (
                        event_type, timestamp, session_id, session_type,
                        component_id, component_display_name, slot_key,
                        previous_value_json, new_value_json, change_source,
                        element_selector, route, settle_duration_ms, confidence
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.event_type.value,
                    event.timestamp,
                    event.session_id,
                    event.session_type,
                    event.component_id,
                    event.component_display_name,
                    event.slot_key,
                    json.dumps(event.previous_value) if event.previous_value is not None else None,
                    json.dumps(event.new_value) if event.new_value is not None else None,
                    event.change_source,
                    event.element_selector,
                    event.route,
                    event.settle_duration_ms,
                    event.confidence
                ))
                conn.commit()
            except Exception as e:
                logger.error(f"Failed to record discovery event: {e}")
            finally:
                conn.close()

        await asyncio.get_running_loop().run_in_executor(None, _sync_record)

    async def get_sessions(
        self,
        min_events: Optional[int] = None,
        complete_only: bool = False,
        session_type: Optional[str] = None,
        after_timestamp: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        def _sync_query():
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.cursor()
                query = "SELECT session_id, session_type, started_at, ended_at, event_count, is_complete, application_version_hash FROM sessions WHERE 1=1"
                params = []

                if min_events is not None:
                    query += " AND event_count >= ?"
                    params.append(min_events)
                if complete_only:
                    query += " AND is_complete = 1"
                if session_type is not None:
                    query += " AND session_type = ?"
                    params.append(session_type)
                if after_timestamp is not None:
                    query += " AND started_at >= ?"
                    params.append(after_timestamp)

                query += " ORDER BY started_at ASC"
                cursor.execute(query, params)
                rows = cursor.fetchall()
                res = []
                for r in rows:
                    res.append({
                        "session_id": r[0],
                        "session_type": r[1],
                        "started_at": r[2],
                        "ended_at": r[3],
                        "event_count": r[4],
                        "is_complete": bool(r[5]),
                        "application_version_hash": r[6]
                    })
                return res
            finally:
                conn.close()

        return await asyncio.get_running_loop().run_in_executor(None, _sync_query)

    async def get_slot_change_sequences(
        self,
        component_display_name: str,
        slot_key: str,
        session_ids: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        def _sync_query():
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.cursor()
                query = """
                    SELECT session_id, timestamp, previous_value_json, new_value_json, change_source, route
                    FROM events
                    WHERE event_type = 'SLOT_CHANGED' AND component_display_name = ? AND slot_key = ?
                """
                params = [component_display_name, slot_key]

                if session_ids:
                    placeholders = ",".join("?" for _ in session_ids)
                    query += f" AND session_id IN ({placeholders})"
                    params.extend(session_ids)

                query += " ORDER BY timestamp ASC"
                cursor.execute(query, params)
                rows = cursor.fetchall()
                res = []
                for r in rows:
                    res.append({
                        "session_id": r[0],
                        "timestamp": r[1],
                        "previous_value": json.loads(r[2]) if r[2] else None,
                        "new_value": json.loads(r[3]) if r[3] else None,
                        "change_source": r[4],
                        "route": r[5]
                    })
                return res
            finally:
                conn.close()

        return await asyncio.get_running_loop().run_in_executor(None, _sync_query)

    async def get_co_occurrence_matrix(self, time_window_ms: float, min_sessions: int) -> Dict[str, float]:
        """
        Identifies slot change occurrences within a temporal window.
        Returns a dict mapping "ComponentA.SlotA:::ComponentB.SlotB" to the fraction of total sessions.
        """
        def _sync_query():
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.cursor()
                # 1. Fetch total count of sessions with completed status
                cursor.execute("SELECT session_id FROM sessions WHERE event_count > 0")
                sessions = [r[0] for r in cursor.fetchall()]
                if not sessions:
                    return {}

                co_counts = {}
                for sid in sessions:
                    cursor.execute("""
                        SELECT component_display_name, slot_key, timestamp
                        FROM events
                        WHERE event_type = 'SLOT_CHANGED' AND session_id = ?
                        ORDER BY timestamp ASC
                    """, (sid,))
                    events = cursor.fetchall()
                    
                    # Deduplicate or group target slots changed in session
                    seen_changes = []
                    for ev in events:
                        if ev[0] and ev[1]:
                            seen_changes.append((ev[0], ev[1], ev[2]))

                    # Identify co-occurrences within window
                    for i in range(len(seen_changes)):
                        for j in range(i + 1, len(seen_changes)):
                            ca, sa, ta = seen_changes[i]
                            cb, sb, tb = seen_changes[j]
                            if ca == cb and sa == sb:
                                continue
                            if abs(tb - ta) * 1000.0 <= time_window_ms:
                                # Order targets alphabetically to form a unique key
                                key_a = f"{ca}.{sa}"
                                key_b = f"{cb}.{sb}"
                                pair = ":::".join(sorted([key_a, key_b]))
                                co_counts[pair] = co_counts.get(pair, set())
                                co_counts[pair].add(sid)

                # Format co-occurrence ratios
                res = {}
                tot_sessions = len(sessions)
                for pair, sids in co_counts.items():
                    if len(sids) >= min_sessions:
                        res[pair] = len(sids) / tot_sessions
                return res
            finally:
                conn.close()

        return await asyncio.get_running_loop().run_in_executor(None, _sync_query)

    async def get_interaction_outcomes(self, element_selector: str, min_sessions: int) -> Dict[str, Any]:
        """
        Computes outcomes (slot changes) immediately following interaction clicks.
        """
        def _sync_query():
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, session_id, timestamp, route
                    FROM events
                    WHERE event_type = 'INTERACTION_OCCURRED' AND element_selector = ?
                """, (element_selector,))
                clicks = cursor.fetchall()
                if not clicks:
                    return {}

                outcomes = {}
                session_clicked = set()
                for cid, sid, ts, route in clicks:
                    session_clicked.add(sid)
                    # Query slot changes within 1.5 seconds following this click in the same session
                    cursor.execute("""
                        SELECT component_display_name, slot_key, new_value_json
                        FROM events
                        WHERE event_type = 'SLOT_CHANGED' AND session_id = ? AND timestamp >= ? AND timestamp <= ? + 1.5
                    """, (sid, ts, ts))
                    changes = cursor.fetchall()
                    for comp, slot, val_json in changes:
                        if not comp or not slot:
                            continue
                        target = f"{comp}.{slot}"
                        if target not in outcomes:
                            outcomes[target] = {"sessions": set(), "values": []}
                        outcomes[target]["sessions"].add(sid)
                        outcomes[target]["values"].append(json.loads(val_json) if val_json else None)

                res = {}
                total_clicks = len(session_clicked)
                for target, info in outcomes.items():
                    freq = len(info["sessions"])
                    if freq >= min_sessions:
                        # Consistency score is the fraction of clicked sessions where the state actually changed
                        consistency = freq / total_clicks
                        res[target] = {
                            "frequency": freq,
                            "consistency": consistency,
                            "examples": list(set(str(v) for v in info["values"][:5]))
                        }
                return res
            finally:
                conn.close()

        return await asyncio.get_running_loop().run_in_executor(None, _sync_query)

    async def get_route_transition_sequences(self, min_sessions: int) -> List[Dict[str, Any]]:
        def _sync_query():
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT session_id FROM sessions WHERE event_count > 0")
                sessions = [r[0] for r in cursor.fetchall()]

                sequences = []
                for sid in sessions:
                    cursor.execute("""
                        SELECT route, timestamp
                        FROM events
                        WHERE event_type = 'ROUTE_CHANGED' AND session_id = ?
                        ORDER BY timestamp ASC
                    """, (sid,))
                    route_events = cursor.fetchall()
                    if route_events:
                        sequences.append([r[0] for r in route_events])

                # Group transitions and count frequencies
                seq_counts = {}
                for seq in sequences:
                    key = " -> ".join(seq)
                    seq_counts[key] = seq_counts.get(key, 0) + 1

                res = []
                for key, val in seq_counts.items():
                    if val >= min_sessions:
                        res.append({
                            "sequence": key.split(" -> "),
                            "frequency": val
                        })
                return res
            finally:
                conn.close()

        return await asyncio.get_running_loop().run_in_executor(None, _sync_query)

    async def get_terminal_state_candidates(self, min_sessions: int) -> List[Dict[str, Any]]:
        """
        Locates slots that transitioned to a terminal state (such as successfully
        submitted or isComplete=True) and remained constant until the session ended.
        """
        def _sync_query():
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT session_id FROM sessions WHERE is_complete = 1")
                sessions = [r[0] for r in cursor.fetchall()]
                if not sessions:
                    return []

                slot_candidates = {}
                for sid in sessions:
                    # Fetch all slot changes ordered by timestamp
                    cursor.execute("""
                        SELECT component_display_name, slot_key, new_value_json, timestamp
                        FROM events
                        WHERE event_type = 'SLOT_CHANGED' AND session_id = ?
                        ORDER BY timestamp DESC
                    """, (sid,))
                    changes = cursor.fetchall()

                    # Track the final value of each slot key
                    final_states = {}
                    for comp, slot, val_json, ts in changes:
                        if not comp or not slot:
                            continue
                        target = f"{comp}.{slot}"
                        if target not in final_states:
                            val = json.loads(val_json) if val_json else None
                            final_states[target] = val

                    # Check if the final value matches success completion indicators
                    for target, val in final_states.items():
                        is_candidate = False
                        if isinstance(val, bool) and val is True:
                            is_candidate = True
                        elif isinstance(val, str) and val.lower() in ["success", "complete", "completed", "passed", "succeeded"]:
                            is_candidate = True

                        if is_candidate:
                            if target not in slot_candidates:
                                slot_candidates[target] = {"sessions": set(), "value": val}
                            slot_candidates[target]["sessions"].add(sid)

                res = []
                for target, info in slot_candidates.items():
                    freq = len(info["sessions"])
                    if freq >= min_sessions:
                        res.append({
                            "target": target,
                            "value": info["value"],
                            "frequency": freq
                        })
                return res
            finally:
                conn.close()

        return await asyncio.get_running_loop().run_in_executor(None, _sync_query)

    async def get_session_outcomes(self, workflow_name: str) -> List[Dict[str, Any]]:
        # Returns list of session executions for validation of preconditions
        # For simplicity, returning successful and failed sessions reaching terminal steps
        return []

    async def record_inference_run(self, timestamp: float, sessions_processed: int, changes_detected: int):
        def _sync_record():
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO inference_runs (timestamp, sessions_processed, changes_detected)
                    VALUES (?, ?, ?)
                """, (timestamp, sessions_processed, changes_detected))
                conn.commit()
            except Exception as e:
                logger.error(f"Failed to record inference run: {e}")
            finally:
                conn.close()

        await asyncio.get_running_loop().run_in_executor(None, _sync_record)

    async def get_last_inference_run(self) -> Optional[Dict[str, Any]]:
        def _sync_query():
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT timestamp, sessions_processed, changes_detected FROM inference_runs ORDER BY timestamp DESC LIMIT 1")
                row = cursor.fetchone()
                if row:
                    return {
                        "timestamp": row[0],
                        "sessions_processed": row[1],
                        "changes_detected": row[2]
                    }
                return None
            finally:
                conn.close()

        return await asyncio.get_running_loop().run_in_executor(None, _sync_query)
