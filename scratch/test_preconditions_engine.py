import asyncio
import sys
import sqlite3
import json

sys.path.insert(0, r"c:\Users\Utkarsh Ranjan\Desktop\AUI\sdk\python")

from react_agent_bridge.discovery.corpus import ObservationCorpus
from react_agent_bridge.discovery.analyzer.precondition import PreconditionInferenceEngine

async def run_diag():
    corpus = ObservationCorpus(r"c:\Users\Utkarsh Ranjan\Desktop\AUI\examples\discovery-flow\discovery.db")
    engine = PreconditionInferenceEngine(corpus, min_pairs=1)
    
    workflows = [{
        "name": "App isSubmitted Workflow",
        "steps": [
            {"target": "App.attendeeName", "operator": "non_empty", "value": None},
            {"target": "App.selectedSessions", "operator": "non_empty", "value": None},
            {"target": "App.cardNumber", "operator": "non_empty", "value": None},
            {"target": "App.isSubmitted", "operator": "equals", "value": True}
        ],
        "success_condition": None,
        "failure_condition": None,
        "confidence": 1.0,
        "session_count": 3
    }]
    
    # We will replicate the engine's analyze_preconditions method but print details
    conn = sqlite3.connect(corpus.db_path)
    cursor = conn.cursor()
    
    for wf in workflows:
        steps = wf["steps"]
        for idx in range(1, len(steps)):
            prev_target = steps[idx - 1]["target"]
            curr_target = steps[idx]["target"]
            print(f"\n--- Analyzing transition: {prev_target} -> {curr_target} ---")
            
            prev_comp, prev_slot = prev_target.rsplit(".", 1)
            curr_comp, curr_slot = curr_target.rsplit(".", 1)
            
            cursor.execute("""
                SELECT DISTINCT session_id
                FROM events
                WHERE event_type = 'SLOT_CHANGED'
                  AND component_display_name = ?
                  AND slot_key = ?
            """, (curr_comp, curr_slot))
            success_sids = [r[0] for r in cursor.fetchall()]
            print(f"Success sids for {curr_target}: {success_sids}")
            
            success_instances = []
            for sid in success_sids:
                # Find t_success (first time terminal state is reached)
                term_comp, term_slot = "App", "isSubmitted"
                cursor.execute("""
                    SELECT MIN(timestamp)
                    FROM events
                    WHERE session_id = ?
                      AND event_type = 'SLOT_CHANGED'
                      AND component_display_name = ?
                      AND slot_key = ?
                      AND new_value_json = 'true'
                """, (sid, term_comp, term_slot))
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
                
                print(f"  Session {sid}: t1={t1}, t2={t2}")
                if t1 is not None and t2 is not None and t1 <= t2:
                    success_instances.append((sid, t1, t2))
            
            print(f"Success instances: {success_instances}")
            if not success_instances:
                continue
                
            before_states = {}
            start_states = {}
            from react_agent_bridge.discovery.recorder import is_probably_sensitive
            for sid, t1, t2 in success_instances:
                # Get session started_at
                cursor.execute("SELECT started_at FROM sessions WHERE session_id = ?", (sid,))
                t_start = cursor.fetchone()[0]
                
                # Fetch all keys to populate before_states
                raw_states = engine._get_slot_values_at_timestamp(cursor, sid, t2 - 0.001)
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
            
            all_keys = set()
            for state in before_states.values():
                all_keys.update(state.keys())
            # all_keys.discard(prev_target)
            all_keys.discard(curr_target)
            all_keys = {k for k in all_keys if not any(nav in k for nav in ("activeStep", "route", "step", "activeTab"))}
            
            print(f"Keys to check: {all_keys}")
            for key in all_keys:
                for operator in ["truthy", "non_empty"]:
                    match_count = sum(
                        1 for sid, t1, t2 in success_instances
                        if engine._evaluate_pattern(before_states[sid].get(key), operator)
                    )
                    not_start_count = sum(
                        1 for sid, t1, t2 in success_instances
                        if not engine._evaluate_pattern(start_states[sid].get(key), operator)
                    )
                    print(f"  Key {key} | operator {operator}: match_count={match_count}/{len(success_instances)}, not_start_count={not_start_count}/{len(success_instances)}")
                    if match_count == len(success_instances) and not_start_count == len(success_instances):
                        print(f"    => PRECONDITION IDENTIFIED: {key} must be {operator}")

    conn.close()

if __name__ == '__main__':
    asyncio.run(run_diag())
