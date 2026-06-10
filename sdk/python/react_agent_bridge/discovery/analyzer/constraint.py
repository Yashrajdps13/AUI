import sqlite3
import json
import logging
from typing import Dict, Any, List, Optional
from react_agent_bridge.discovery.corpus import ObservationCorpus

logger = logging.getLogger("react_agent_bridge.discovery.analyzer.constraint")


class ConstraintInferenceEngine:
    """
    Identifies invariants in the corpus — patterns that were never violated
    across all observed sessions — and proposes them as constraints.
    """
    def __init__(self, corpus: ObservationCorpus, min_sessions: int = 5):
        self.corpus = corpus
        self.min_sessions = min_sessions
        self._constraints: Dict[str, Dict[str, Any]] = {}
        self._comp_routes: Dict[str, Set[str]] = {}

    def _get_slot_values_at_timestamp(self, cursor: sqlite3.Cursor, session_id: str, timestamp: float) -> Dict[str, Any]:
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

    def _evaluate_pattern(self, val: Any, operator: str) -> bool:
        if operator == "truthy":
            return bool(val)
        elif operator == "non_empty":
            if val is None:
                return False
            if isinstance(val, (str, list, dict)):
                return len(val) > 0
            return True
        return False

    async def analyze(self, slot_annotations: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analyzes the corpus and returns a list of inferred constraints.
        """
        # Determine if we should run incrementally
        last_run = await self.corpus.get_last_inference_run()
        after_ts = None
        if last_run and self._constraints:
            after_ts = last_run["timestamp"]

        new_constraints = {}
        conn = sqlite3.connect(self.corpus.db_path)
        try:
            cursor = conn.cursor()

            # Get total sessions count for metadata
            cursor.execute("SELECT COUNT(*) FROM sessions WHERE is_complete = 1")
            total_sessions = cursor.fetchone()[0] or self.min_sessions

            # 1. Sequencing constraints
            # Find slot changes that have occurred (optionally since after_ts)
            query_targets = """
                SELECT DISTINCT component_display_name, slot_key
                FROM events
                WHERE event_type = 'SLOT_CHANGED'
            """
            params_targets = []
            if after_ts:
                query_targets += " AND timestamp >= ?"
                params_targets.append(after_ts)
            
            cursor.execute(query_targets, params_targets)
            targets = [f"{r[0]}.{r[1]}" for r in cursor.fetchall() if r[0] and r[1]]

            for target in targets:
                comp_name, slot_key = target.rsplit(".", 1)

                # Get occurrences of this target across sessions
                cursor.execute("""
                    SELECT session_id, timestamp
                    FROM events
                    WHERE event_type = 'SLOT_CHANGED'
                      AND component_display_name = ?
                      AND slot_key = ?
                    ORDER BY session_id, timestamp ASC
                """, (comp_name, slot_key))
                occurrences = cursor.fetchall()

                # Group by session_id to get one first-occurrence per session
                unique_occurrences = {}
                for sid, ts in occurrences:
                    if sid not in unique_occurrences:
                        unique_occurrences[sid] = ts

                if len(unique_occurrences) < self.min_sessions:
                    continue

                # Query the state immediately before each occurrence
                before_states = [
                    self._get_slot_values_at_timestamp(cursor, sid, ts - 0.001)
                    for sid, ts in unique_occurrences.items()
                ]

                # Find all slot keys that exist in these states
                all_keys = set()
                for state in before_states:
                    all_keys.update(state.keys())
                all_keys.discard(target)

                # Find if any key consistently satisfies a condition in 100% of cases
                for key in all_keys:
                    for op in ["truthy", "non_empty"]:
                        match_count = sum(
                            1 for state in before_states
                            if self._evaluate_pattern(state.get(key), op)
                        )
                        if match_count == len(before_states):
                            # We found an invariant sequencing constraint!
                            c_name = f"Seq_{comp_name}_{slot_key}_requires_{key.replace('.', '_')}"
                            new_constraints[c_name] = {
                                "name": c_name,
                                "status": "INFERRED",
                                "constraint_type": "sequencing",
                                "confidence": 1.0,
                                "session_count": len(before_states),
                                "evidence_summary": f"In all {len(before_states)} observed sessions where {target} changed, {key} was already {op}.",
                                "description": f"The state slot {target} should only be updated when {key} is {op}.",
                                "target": target
                            }

            # 2. Write-protection constraints
            # Propose write-protection for all slots annotated as is_derived=True
            for target, ann in slot_annotations.items():
                if ann.get("is_derived") and ann.get("confidence", 0.0) >= 0.5:
                    comp_name, slot_key = target.rsplit(".", 1)
                    c_name = f"WP_{comp_name}_{slot_key}"
                    new_constraints[c_name] = {
                        "name": c_name,
                        "status": "INFERRED",
                        "constraint_type": "write-protection",
                        "confidence": ann.get("confidence", 1.0),
                        "session_count": total_sessions,
                        "evidence_summary": f"State slot {target} is derived and never changes in isolation.",
                        "description": f"The state slot {target} is read-only or derived and should not be directly mutated.",
                        "target": target
                    }

            # 3. Scope constraints
            # Components observed only on specific routes
            query_routes = """
                SELECT DISTINCT component_display_name, route
                FROM events
                WHERE route IS NOT NULL AND component_display_name IS NOT NULL
            """
            params_routes = []
            if after_ts:
                query_routes += " AND timestamp >= ?"
                params_routes.append(after_ts)

            cursor.execute(query_routes, params_routes)
            route_mounts = cursor.fetchall()
            
            for comp, rt in route_mounts:
                if comp not in self._comp_routes:
                    self._comp_routes[comp] = set()
                self._comp_routes[comp].add(rt)

            # Re-evaluate scope constraints based on full accumulated comp_routes
            for comp, rts in self._comp_routes.items():
                if len(rts) <= 2:
                    c_name = f"Scope_{comp}"
                    new_constraints[c_name] = {
                        "name": c_name,
                        "status": "INFERRED",
                        "constraint_type": "scope",
                        "confidence": 1.0,
                        "session_count": total_sessions,
                        "evidence_summary": f"Component {comp} was only observed mounted on routes: {sorted(list(rts))}.",
                        "description": f"Component {comp} is scoped and should only be accessed on routes: {sorted(list(rts))}.",
                        "target": comp
                    }

            # Merge or set constraints
            if after_ts:
                # Merge new inferences with existing ones
                for name, new_c in new_constraints.items():
                    if name in self._constraints:
                        old_c = self._constraints[name]
                        old_c["session_count"] = max(old_c["session_count"], new_c["session_count"])
                        old_c["evidence_summary"] = new_c["evidence_summary"]
                    else:
                        self._constraints[name] = new_c
            else:
                self._constraints = new_constraints

        except Exception as e:
            logger.error(f"Error in ConstraintInferenceEngine: {e}", exc_info=True)
        finally:
            conn.close()

        # Hard safety guarantee: status must strictly be INFERRED
        for c in self._constraints.values():
            c["status"] = "INFERRED"

        return sorted(self._constraints.values(), key=lambda x: x["name"])
