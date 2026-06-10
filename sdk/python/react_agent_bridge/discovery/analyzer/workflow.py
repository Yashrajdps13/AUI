import sqlite3
import json
import time
import logging
from typing import Dict, Any, List, Optional
from react_agent_bridge.discovery.corpus import ObservationCorpus
from react_agent_bridge.core.planner.goal import GoalCondition

logger = logging.getLogger("react_agent_bridge.discovery.analyzer.workflow")


class WorkflowInferenceEngine:
    """
    Identifies recurring multi-step patterns in the corpus and describes
    them as named workflows with success and failure conditions.
    """
    def __init__(self, corpus: ObservationCorpus):
        self.corpus = corpus
        self._workflows: Dict[str, Dict[str, Any]] = {}
        self.last_run_timestamp: float = 0.0

    async def analyze(self, min_confidence: float = 0.6) -> List[Dict[str, Any]]:
        """
        Runs incremental workflow inference and updates the internal workflows cache.
        Returns the list of active workflows sorted by confidence descending.
        """
        # Determine if we should run incrementally
        last_run = await self.corpus.get_last_inference_run()
        after_ts = None
        if last_run and self._workflows:
            after_ts = last_run["timestamp"]

        # 1. Fetch sessions
        sessions = await self.corpus.get_sessions(complete_only=True, after_timestamp=after_ts)
        new_session_ids = [s["session_id"] for s in sessions if s["event_count"] > 0]

        if not new_session_ids:
            # No new completed sessions to process; return existing workflows
            return sorted(self._workflows.values(), key=lambda w: w["confidence"], reverse=True)

        # Connect to DB to execute structured sequence queries
        conn = sqlite3.connect(self.corpus.db_path)
        try:
            cursor = conn.cursor()

            # Group sessions by version hash
            cursor.execute("SELECT session_id, application_version_hash FROM sessions")
            session_versions = {r[0]: r[1] for r in cursor.fetchall()}

            # Find the most recent session's version hash
            cursor.execute("SELECT application_version_hash FROM sessions ORDER BY ended_at DESC LIMIT 1")
            latest_version_row = cursor.fetchone()
            latest_version = latest_version_row[0] if latest_version_row else "initial_v1"

            def get_weight(sid):
                v = session_versions.get(sid, "initial_v1")
                return 1.0 if v == latest_version else 0.2

            # 2. Get terminal candidates
            cursor.execute("""
                SELECT component_display_name, slot_key, new_value_json, COUNT(DISTINCT session_id) as freq
                FROM events
                WHERE event_type = 'SLOT_CHANGED'
                  AND (new_value_json = 'true' OR lower(new_value_json) IN ('"success"', '"complete"', '"completed"', '"passed"', '"succeeded"'))
                GROUP BY component_display_name, slot_key, new_value_json
                HAVING freq >= 1
            """)
            candidates = cursor.fetchall()

            for comp_name, slot_key, val_json, total_freq in candidates:
                if not comp_name or not slot_key:
                    continue
                terminal_target = f"{comp_name}.{slot_key}"
                terminal_val = json.loads(val_json) if val_json else True

                # Find all sessions where this terminal state was reached
                cursor.execute("""
                    SELECT DISTINCT session_id
                    FROM events
                    WHERE event_type = 'SLOT_CHANGED'
                      AND component_display_name = ?
                      AND slot_key = ?
                      AND new_value_json = ?
                """, (comp_name, slot_key, val_json))
                success_session_ids = [r[0] for r in cursor.fetchall()]
                if not success_session_ids:
                    continue

                # Filter success sessions to those in our current batch if running incrementally
                batch_success_ids = [sid for sid in success_session_ids if sid in new_session_ids]
                if after_ts and not batch_success_ids:
                    # No new sessions reached this terminal state in this batch
                    continue

                # Query all slot changes in the success sessions (to build/update sequence)
                placeholders = ",".join("?" for _ in success_session_ids)
                cursor.execute(f"""
                    SELECT session_id, component_display_name, slot_key, new_value_json, timestamp, route
                    FROM events
                    WHERE session_id IN ({placeholders})
                      AND event_type = 'SLOT_CHANGED'
                    ORDER BY session_id, timestamp ASC
                """, success_session_ids)
                events = cursor.fetchall()

                # Group events by session
                session_events: Dict[str, List[tuple]] = {}
                for r in events:
                    sid = r[0]
                    if sid not in session_events:
                        session_events[sid] = []
                    session_events[sid].append((r[1], r[2], r[3], r[4], r[5]))

                # Count frequency and calculate average order of each non-terminal change
                slot_counts: Dict[str, float] = {}
                slot_positions: Dict[str, List[int]] = {}
                slot_values: Dict[str, Dict[str, int]] = {}
                slot_routes: Dict[str, set] = {}

                for sid, evs in session_events.items():
                    # Filter out noise (slots that changed > 20 times in a single session)
                    counts_in_session: Dict[str, int] = {}
                    for comp, slot, val_j, ts, rt in evs:
                        t_key = f"{comp}.{slot}"
                        counts_in_session[t_key] = counts_in_session.get(t_key, 0) + 1

                    filtered_evs = [
                        (comp, slot, val_j, ts, rt)
                        for comp, slot, val_j, ts, rt in evs
                        if counts_in_session[f"{comp}.{slot}"] <= 20 and f"{comp}.{slot}" != terminal_target
                    ]

                    # Map unique slot change order in this session
                    seen_slots = set()
                    for pos, (comp, slot, val_j, ts, rt) in enumerate(filtered_evs):
                        t_key = f"{comp}.{slot}"
                        if t_key not in seen_slots:
                            seen_slots.add(t_key)
                            slot_counts[t_key] = slot_counts.get(t_key, 0.0) + get_weight(sid)
                            if t_key not in slot_positions:
                                slot_positions[t_key] = []
                            slot_positions[t_key].append(pos)

                            if t_key not in slot_values:
                                slot_values[t_key] = {}
                            slot_values[t_key][val_j] = slot_values[t_key].get(val_j, 0) + 1

                            if t_key not in slot_routes:
                                slot_routes[t_key] = set()
                            if rt:
                                slot_routes[t_key].add(rt)

                # Steps are slots changed in >= 50% of success sessions
                num_success_sessions = sum(get_weight(sid) for sid in success_session_ids)
                step_candidates = []
                for t_key, count in slot_counts.items():
                    ratio = count / num_success_sessions if num_success_sessions > 0 else 0.0
                    if ratio >= 0.5:
                        avg_pos = sum(slot_positions[t_key]) / len(slot_positions[t_key])
                        # Find most common value json
                        most_common_val_json = max(slot_values[t_key].items(), key=lambda x: x[1])[0]
                        try:
                            mcv = json.loads(most_common_val_json) if most_common_val_json else None
                        except Exception:
                            mcv = most_common_val_json
                        
                        step_candidates.append({
                            "target": t_key,
                            "avg_pos": avg_pos,
                            "value": mcv,
                            "routes": list(slot_routes[t_key])
                        })

                # Sort steps by average order of appearance
                step_candidates.sort(key=lambda x: x["avg_pos"])

                steps = []
                for s in step_candidates:
                    comp_name, s_key = s["target"].rsplit(".", 1)
                    op = "equals" if s["value"] is not None else "truthy"
                    steps.append({
                        "target": s["target"],
                        "operator": op,
                        "value": s["value"],
                        "description": f"Set {s_key} on {comp_name}"
                    })

                # If no workflow steps are identified, skip this candidate
                if not steps:
                    continue

                # 3. Identify failure conditions in stalled/failed sessions
                # Failed sessions: completed sessions that did not reach success, but changed >= 50% of workflow step slots
                workflow_slots = {s["target"] for s in steps}
                cursor.execute("SELECT session_id FROM sessions WHERE is_complete = 1")
                all_completed_ids = [r[0] for r in cursor.fetchall()]
                failed_session_ids = [sid for sid in all_completed_ids if sid not in success_session_ids]

                failure_cond = None
                if failed_session_ids:
                    # Filter to sessions changing at least half of the steps
                    qualifying_failed_ids = []
                    for fsid in failed_session_ids:
                        cursor.execute("""
                            SELECT DISTINCT component_display_name || '.' || slot_key
                            FROM events
                            WHERE session_id = ? AND event_type = 'SLOT_CHANGED'
                        """, (fsid,))
                        changed_slots = {r[0] for r in cursor.fetchall()}
                        intersection = changed_slots.intersection(workflow_slots)
                        if len(intersection) >= len(workflow_slots) / 2:
                            qualifying_failed_ids.add(fsid) if hasattr(qualifying_failed_ids, 'add') else qualifying_failed_ids.append(fsid)

                    if qualifying_failed_ids:
                        # Scan qualifying failed sessions for any slot containing error, failed, invalid, or err
                        placeholders_fail = ",".join("?" for _ in qualifying_failed_ids)
                        cursor.execute(f"""
                            SELECT component_display_name, slot_key, new_value_json
                            FROM events
                            WHERE session_id IN ({placeholders_fail})
                              AND event_type = 'SLOT_CHANGED'
                              AND (lower(slot_key) LIKE '%error%' OR lower(slot_key) LIKE '%failed%' OR lower(slot_key) LIKE '%invalid%' OR lower(slot_key) LIKE '%err%')
                        """, qualifying_failed_ids)
                        fail_changes = cursor.fetchall()
                        if fail_changes:
                            # Group by target to find most common error slot
                            fail_counts = {}
                            fail_values = {}
                            for fc_comp, fc_slot, fc_val_j in fail_changes:
                                fc_target = f"{fc_comp}.{fc_slot}"
                                fail_counts[fc_target] = fail_counts.get(fc_target, 0) + 1
                                fail_values[fc_target] = fc_val_j

                            best_fail_target = max(fail_counts.items(), key=lambda x: x[1])[0]
                            best_fail_val_json = fail_values[best_fail_target]
                            try:
                                best_fail_val = json.loads(best_fail_val_json) if best_fail_val_json else True
                            except Exception:
                                best_fail_val = best_fail_val_json

                            if best_fail_val:
                                failure_cond = GoalCondition(
                                    target=best_fail_target,
                                    operator="equals" if best_fail_val is not True else "truthy",
                                    value=best_fail_val if best_fail_val is not True else None
                                )

                # Calculate confidence: success sessions / total sessions attempting the workflow steps
                attempted_session_ids = set(success_session_ids)
                if failed_session_ids:
                    for fsid in failed_session_ids:
                        cursor.execute("""
                            SELECT DISTINCT component_display_name || '.' || slot_key
                            FROM events
                            WHERE session_id = ? AND event_type = 'SLOT_CHANGED'
                        """, (fsid,))
                        changed_slots = {r[0] for r in cursor.fetchall()}
                        if changed_slots.intersection(workflow_slots):
                            attempted_session_ids.add(fsid)

                confidence = sum(get_weight(sid) for sid in success_session_ids) / sum(get_weight(sid) for sid in attempted_session_ids) if attempted_session_ids else 0.0

                # 4. Get last seen timestamp
                cursor.execute("""
                    SELECT MAX(timestamp)
                    FROM events
                    WHERE session_id IN ({placeholders})
                """.format(placeholders=",".join("?" for _ in success_session_ids)), success_session_ids)
                last_seen = cursor.fetchone()[0] or time.time()

                # Generate a clean, descriptive name
                wf_name = f"{comp_name} {slot_key} Workflow".replace("Store", "").replace("Panel", "").strip()

                success_cond = GoalCondition(target=terminal_target, operator="equals", value=terminal_val)

                # Merge/update internal state
                if wf_name in self._workflows:
                    old_wf = self._workflows[wf_name]
                    # Update metrics incrementally
                    old_count = old_wf["session_count"]
                    new_count = len(batch_success_ids)
                    old_wf["session_count"] = len(success_session_ids)
                    old_wf["last_seen"] = max(old_wf["last_seen"], last_seen)
                    if new_count > 0:
                        old_wf["confidence"] = (old_wf["confidence"] * old_count + confidence * new_count) / (old_count + new_count)
                        old_wf["steps"] = steps  # Update step definition if sequence refined
                else:
                    self._workflows[wf_name] = {
                        "name": wf_name,
                        "steps": steps,
                        "success_condition": success_cond,
                        "failure_condition": failure_cond,
                        "confidence": confidence,
                        "session_count": len(success_session_ids),
                        "last_seen": last_seen
                    }

        except Exception as e:
            logger.error(f"Error executing workflow inference: {e}", exc_info=True)
        finally:
            conn.close()

        # Update the execution run history in corpus
        self.last_run_timestamp = time.time()
        await self.corpus.record_inference_run(
            timestamp=self.last_run_timestamp,
            sessions_processed=len(new_session_ids),
            changes_detected=len(self._workflows)
        )

        # Filter by minimum confidence threshold
        active_wfs = [w for w in self._workflows.values() if w["confidence"] >= min_confidence]
        return sorted(active_wfs, key=lambda w: w["confidence"], reverse=True)
