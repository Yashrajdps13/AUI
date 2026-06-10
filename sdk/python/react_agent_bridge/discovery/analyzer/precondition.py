import sqlite3
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from react_agent_bridge.discovery.corpus import ObservationCorpus
from react_agent_bridge.discovery.recorder import is_probably_sensitive

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

                    # Get terminal target details from the last step of the workflow
                    term_step = steps[-1]
                    term_target = term_step["target"]
                    term_comp, term_slot = term_target.rsplit(".", 1)
                    term_val = term_step["value"]
                    term_val_json = json.dumps(term_val)

                    # 1. Fetch success sessions for this workflow (reached success condition)
                    cursor.execute("""
                        SELECT DISTINCT session_id
                        FROM events
                        WHERE event_type = 'SLOT_CHANGED'
                          AND component_display_name = ?
                          AND slot_key = ?
                          AND new_value_json = ?
                    """, (term_comp, term_slot, term_val_json))
                    success_sids = [r[0] for r in cursor.fetchall()]

                    if not success_sids:
                        continue

                    # 2. In each session, find T1 (last change to prev_target before t_success)
                    # and T2 (last change to curr_target before t_success)
                    success_instances = []
                    for sid in success_sids:
                        # Find t_success (first time terminal state is reached)
                        cursor.execute("""
                            SELECT MIN(timestamp)
                            FROM events
                            WHERE session_id = ?
                              AND event_type = 'SLOT_CHANGED'
                              AND component_display_name = ?
                              AND slot_key = ?
                              AND new_value_json = ?
                        """, (sid, term_comp, term_slot, term_val_json))
                        t_success_row = cursor.fetchone()
                        t_success = t_success_row[0] if t_success_row else None
                        if not t_success:
                            # Fallback to last event timestamp in session
                            cursor.execute("SELECT MAX(timestamp) FROM events WHERE session_id = ?", (sid,))
                            t_success = cursor.fetchone()[0]
                        if not t_success:
                            continue

                        # Find last change to prev_target before t_success
                        cursor.execute("""
                            SELECT MAX(timestamp)
                            FROM events
                            WHERE session_id = ?
                              AND event_type = 'SLOT_CHANGED'
                              AND component_display_name = ?
                              AND slot_key = ?
                              AND timestamp <= ?
                        """, (sid, prev_comp, prev_slot, t_success))
                        t1 = cursor.fetchone()[0]

                        # Find last change to curr_target before t_success
                        cursor.execute("""
                            SELECT MAX(timestamp)
                            FROM events
                            WHERE session_id = ?
                              AND event_type = 'SLOT_CHANGED'
                              AND component_display_name = ?
                              AND slot_key = ?
                              AND timestamp <= ?
                        """, (sid, curr_comp, curr_slot, t_success))
                        t2 = cursor.fetchone()[0]

                        if t1 is not None and t2 is not None and t1 <= t2:
                            success_instances.append((sid, t1, t2))

                    if not success_instances:
                        continue

                    # 3. Extract slot states immediately before transition (at T2) and at start of session
                    before_states = {}
                    start_states = {}
                    for sid, t1, t2 in success_instances:
                        # Get session started_at
                        cursor.execute("SELECT started_at FROM sessions WHERE session_id = ?", (sid,))
                        t_start = cursor.fetchone()[0]

                        # Fetch all keys to populate before_states
                        raw_states = self._get_slot_values_at_timestamp(cursor, sid, t2 - 0.001)
                        before_states[sid] = {}
                        for k, val in raw_states.items():
                            if is_probably_sensitive(k):
                                # Sensitive check: did it change after mount burst (t_start + 1.0) and before t2?
                                cursor.execute("""
                                    SELECT COUNT(*)
                                    FROM events
                                    WHERE session_id = ?
                                      AND event_type = 'SLOT_CHANGED'
                                      AND component_display_name || '.' || slot_key = ?
                                      AND timestamp > ? AND timestamp <= ?
                                """, (sid, k, t_start + 1.0, t2))
                                count = cursor.fetchone()[0]
                                before_states[sid][k] = "[REDACTED]" if count > 0 else ""
                            else:
                                before_states[sid][k] = val

                        cursor.execute("""
                            SELECT component_display_name || '.' || slot_key, new_value_json
                            FROM events
                            WHERE session_id = ? AND previous_value_json IS NULL
                        """, (sid,))
                        start_states[sid] = {}
                        for k_name, val_j in cursor.fetchall():
                            if k_name and is_probably_sensitive(k_name):
                                start_states[sid][k_name] = ""
                            elif k_name:
                                try:
                                    start_states[sid][k_name] = json.loads(val_j) if val_j else None
                                except Exception:
                                    start_states[sid][k_name] = val_j

                    # Find all unique slot keys across before_states
                    all_keys = set()
                    for state in before_states.values():
                        all_keys.update(state.keys())

                    all_keys.discard(curr_target)
                    # Discard navigation slots
                    all_keys = {k for k in all_keys if not any(nav in k for nav in ("activeStep", "route", "step", "activeTab"))}

                    for key in all_keys:
                        for operator in ["truthy", "non_empty"]:
                            # Check if the condition consistently holds before transition
                            match_count = sum(
                                1 for sid, t1, t2 in success_instances
                                if self._evaluate_pattern(before_states[sid].get(key), operator)
                            )
                            # Check if it was empty at the start of the session
                            not_start_count = sum(
                                1 for sid, t1, t2 in success_instances
                                if not self._evaluate_pattern(start_states[sid].get(key), operator)
                            )
                            
                            # If it holds in 100% of transitions and was not true at the start
                            if match_count == len(success_instances) and not_start_count == len(success_instances):
                                preconditions.append({
                                    "slot_target": key,
                                    "required_condition": f"{key} must be {operator}",
                                    "operator": operator,
                                    "value": None,
                                    "pattern": None,
                                    "confidence": 1.0,
                                    "session_count": len(success_instances)
                                })

                 # De-duplicate preconditions
                unique_preconditions = []
                seen_pre = set()
                for pre in preconditions:
                    pre_key = (pre["slot_target"], pre["operator"])
                    if pre_key not in seen_pre:
                        seen_pre.add(pre_key)
                        unique_preconditions.append(pre)
                self._preconditions[wf_name] = unique_preconditions

        except Exception as e:
            logger.error(f"Error in PreconditionInferenceEngine: {e}", exc_info=True)
        finally:
            conn.close()

        return self._preconditions
