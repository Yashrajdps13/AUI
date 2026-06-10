import sqlite3
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from react_agent_bridge.discovery.corpus import ObservationCorpus

logger = logging.getLogger("react_agent_bridge.discovery.analyzer.precondition")


class PreconditionInferenceEngine:
    """
    For each inferred workflow step, identifies which slot values must
    hold for that step to succeed.
    """
    def __init__(self, corpus: ObservationCorpus, min_pairs: int = 3, confidence_threshold: float = 0.7):
        self.corpus = corpus
        self.min_pairs = min_pairs
        self.confidence_threshold = confidence_threshold
        self._preconditions: Dict[str, List[Dict[str, Any]]] = {}

    def _get_slot_values_at_timestamp(self, cursor: sqlite3.Cursor, session_id: str, timestamp: float) -> Dict[str, Any]:
        """
        Retrieves the state of all slots in a session at a specific timestamp.
        """
        cursor.execute("""
            SELECT component_display_name, slot_key, new_value_json, MAX(timestamp)
            FROM events
            WHERE session_id = ? 
              AND event_type = 'SLOT_CHANGED' 
              AND timestamp <= ?
            GROUP BY component_display_name, slot_key
        """, (session_id, timestamp))
        
        values = {}
        for r in cursor.fetchall():
            comp_name, slot_key, val_json, _ = r
            if comp_name and slot_key:
                try:
                    val = json.loads(val_json) if val_json else None
                except Exception:
                    val = val_json
                values[f"{comp_name}.{slot_key}"] = val
        return values

    def _evaluate_pattern(self, val: Any, operator: str, target_val: Any = None) -> bool:
        if operator == "truthy":
            return bool(val)
        elif operator == "non_empty":
            if val is None:
                return False
            if isinstance(val, (str, list, dict)):
                return len(val) > 0
            return True
        elif operator == "equals":
            return val == target_val
        return False

    async def analyze_preconditions(self, workflows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Analyzes preconditions for the steps of each workflow.
        Returns a dict mapping workflow name to a list of preconditions.
        """
        # Determine if we should run incrementally
        last_run = await self.corpus.get_last_inference_run()
        after_ts = None
        if last_run and self._preconditions:
            after_ts = last_run["timestamp"]

        conn = sqlite3.connect(self.corpus.db_path)
        try:
            cursor = conn.cursor()

            # Query session version weights
            cursor.execute("SELECT session_id, application_version_hash FROM sessions")
            session_versions = {r[0]: r[1] for r in cursor.fetchall()}

            cursor.execute("SELECT application_version_hash FROM sessions ORDER BY ended_at DESC LIMIT 1")
            latest_version_row = cursor.fetchone()
            latest_version = latest_version_row[0] if latest_version_row else "initial_v1"

            def get_weight(sid):
                v = session_versions.get(sid, "initial_v1")
                return 1.0 if v == latest_version else 0.2

            for wf in workflows:
                wf_name = wf["name"]
                steps = wf["steps"]
                preconditions = []

                if len(steps) < 2:
                    # Precondition analysis requires at least a transition between steps
                    if wf_name not in self._preconditions:
                        self._preconditions[wf_name] = []
                    continue

                # Analyze transitions between steps S_{i-1} and S_i
                for idx in range(1, len(steps)):
                    prev_step = steps[idx - 1]
                    curr_step = steps[idx]
                    prev_target = prev_step["target"]
                    curr_target = curr_step["target"]

                    prev_comp, prev_slot = prev_target.rsplit(".", 1)
                    curr_comp, curr_slot = curr_target.rsplit(".", 1)

                    # 1. Identify success and stalled sessions
                    # Success: prev_target changed at T1, curr_target changed at T2 within 10s
                    query_success = """
                        SELECT DISTINCT e1.session_id, e1.timestamp, e2.timestamp
                        FROM events e1
                        JOIN events e2 ON e1.session_id = e2.session_id
                        WHERE e1.event_type = 'SLOT_CHANGED' AND e1.component_display_name = ? AND e1.slot_key = ?
                          AND e2.event_type = 'SLOT_CHANGED' AND e2.component_display_name = ? AND e2.slot_key = ?
                          AND e2.timestamp >= e1.timestamp AND e2.timestamp <= e1.timestamp + 10.0
                    """
                    params_success = [prev_comp, prev_slot, curr_comp, curr_slot]
                    if after_ts:
                        query_success += " AND e1.timestamp >= ?"
                        params_success.append(after_ts)
                    
                    cursor.execute(query_success, params_success)
                    success_sessions = cursor.fetchall()

                    # Stalled: prev_target changed at T1, but curr_target did not change within 10s (or at all)
                    query_stalled = """
                        SELECT DISTINCT e1.session_id, e1.timestamp
                        FROM events e1
                        WHERE e1.event_type = 'SLOT_CHANGED' AND e1.component_display_name = ? AND e1.slot_key = ?
                          AND e1.session_id NOT IN (
                               SELECT DISTINCT session_id
                               FROM events
                               WHERE event_type = 'SLOT_CHANGED' AND component_display_name = ? AND slot_key = ?
                                 AND timestamp >= e1.timestamp AND timestamp <= e1.timestamp + 10.0
                           )
                    """
                    params_stalled = [prev_comp, prev_slot, curr_comp, curr_slot]
                    if after_ts:
                        query_stalled += " AND e1.timestamp >= ?"
                        params_stalled.append(after_ts)
                    
                    cursor.execute(query_stalled, params_stalled)
                    stalled_sessions = cursor.fetchall()

                    if len(success_sessions) < self.min_pairs or len(stalled_sessions) < self.min_pairs:
                        continue

                    # 2. Extract slot values immediately before transition (at T1)
                    success_states = [
                        self._get_slot_values_at_timestamp(cursor, sid, t_prev)
                        for sid, t_prev, _ in success_sessions
                    ]
                    stalled_states = [
                        self._get_slot_values_at_timestamp(cursor, sid, t_prev)
                        for sid, t_prev in stalled_sessions
                    ]

                    # Find all unique slot keys across all states
                    all_keys = set()
                    for state in success_states + stalled_states:
                        all_keys.update(state.keys())

                    # Exclude the step targets themselves to avoid trivial correlation
                    all_keys.discard(prev_target)
                    all_keys.discard(curr_target)

                    # 3. Correlate keys with patterns
                    for key in all_keys:
                        # Patterns to evaluate: "truthy", "non_empty"
                        for operator in ["truthy", "non_empty"]:
                            total_success_weight = sum(get_weight(sid) for (sid, _, _) in success_sessions)
                            total_stalled_weight = sum(get_weight(sid) for (sid, _) in stalled_sessions)

                            # Map indices manually to avoid using range/enumerate loop variables incorrectly
                            success_matches = 0
                            for idx_s, (sid, t_prev, _) in enumerate(success_sessions):
                                if self._evaluate_pattern(success_states[idx_s].get(key), operator):
                                    success_matches += get_weight(sid)

                            stalled_matches = 0
                            for idx_st, (sid, t_prev) in enumerate(stalled_sessions):
                                if self._evaluate_pattern(stalled_states[idx_st].get(key), operator):
                                    stalled_matches += get_weight(sid)

                            success_ratio = success_matches / total_success_weight if total_success_weight > 0 else 0.0
                            stalled_ratio = stalled_matches / total_stalled_weight if total_stalled_weight > 0 else 0.0

                            # Condition: consistently holds in success sessions, violates in stalled sessions
                            if success_ratio >= self.confidence_threshold and stalled_ratio <= (1 - self.confidence_threshold):
                                preconditions.append({
                                    "slot_target": key,
                                    "required_condition": f"{key} must be {operator}",
                                    "operator": operator,
                                    "value": None,
                                    "pattern": None,
                                    "confidence": success_ratio,
                                    "session_count": len(success_sessions)
                                })

                if wf_name not in self._preconditions:
                    self._preconditions[wf_name] = []

                if after_ts:
                    # Merge incrementally
                    for new_pre in preconditions:
                        existing_pre = None
                        for ep in self._preconditions[wf_name]:
                            if ep["slot_target"] == new_pre["slot_target"] and ep["operator"] == new_pre["operator"]:
                                existing_pre = ep
                                break
                        if existing_pre:
                            old_count = existing_pre["session_count"]
                            new_count = new_pre["session_count"]
                            if old_count + new_count > 0:
                                existing_pre["confidence"] = (existing_pre["confidence"] * old_count + new_pre["confidence"] * new_count) / (old_count + new_count)
                            existing_pre["session_count"] = old_count + new_count
                        else:
                            self._preconditions[wf_name].append(new_pre)
                else:
                    self._preconditions[wf_name] = preconditions

        except Exception as e:
            logger.error(f"Error in PreconditionInferenceEngine: {e}", exc_info=True)
        finally:
            conn.close()

        return self._preconditions
