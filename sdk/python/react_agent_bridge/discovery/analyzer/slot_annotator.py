import logging
from typing import Dict, Any, List, Set
from react_agent_bridge.discovery.corpus import ObservationCorpus
from react_agent_bridge.discovery.recorder import is_probably_sensitive

logger = logging.getLogger("react_agent_bridge.discovery.analyzer.slot_annotator")


class SlotAnnotationEngine:
    """
    Analyzes historical corpus events to extract types, constraints, sensitivity,
    volatility, and descriptions for state slots.
    """
    def __init__(self, corpus: ObservationCorpus):
        self.corpus = corpus

    async def analyze(self) -> Dict[str, Dict[str, Any]]:
        """
        Analyzes the corpus and returns a dictionary of:
        { "ComponentDisplayName.slotKey": annotation_dict }
        """
        # Helper to safely load JSON
        def json_loads(s):
            if not s:
                return None
            try:
                import json
                return json.loads(s)
            except Exception:
                return s

        # Fetch all SLOT_CHANGED events from SQLite
        # Let's run a query to get all SLOT_CHANGED events
        sessions = await self.corpus.get_sessions()
        session_ids = [s["session_id"] for s in sessions if s["event_count"] > 0]
        if not session_ids:
            return {}

        conn = sqlite3_connect = self.corpus.db_path
        import sqlite3
        db_conn = sqlite3.connect(sqlite3_connect)
        try:
            cursor = db_conn.cursor()
            cursor.execute("""
                SELECT component_display_name, slot_key, previous_value_json, new_value_json,
                       session_id, timestamp, route
                FROM events
                WHERE event_type = 'SLOT_CHANGED'
                ORDER BY session_id, timestamp ASC
            """)
            rows = cursor.fetchall()
        finally:
            db_conn.close()

        # Group events by (component_display_name, slot_key)
        slots_data: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            comp_name = r[0] or "Unknown"
            slot_key = r[1]
            if not slot_key:
                continue
            key = f"{comp_name}.{slot_key}"
            if key not in slots_data:
                slots_data[key] = []
            slots_data[key].append({
                "previous_value": json_loads(r[2]),
                "new_value": json_loads(r[3]),
                "session_id": r[4],
                "timestamp": r[5],
                "route": r[6]
            })

        annotations = {}
        # Also group all slot change timestamps by (session_id, component_display_name)
        comp_changes_by_session: Dict[str, Dict[str, List[float]]] = {}
        for key, events in slots_data.items():
            for ev in events:
                sid = ev["session_id"]
                comp_name = key.rsplit(".", 1)[0]
                if sid not in comp_changes_by_session:
                    comp_changes_by_session[sid] = {}
                if comp_name not in comp_changes_by_session[sid]:
                    comp_changes_by_session[sid][comp_name] = []
                comp_changes_by_session[sid][comp_name].append(ev["timestamp"])

        for key, events in slots_data.items():
            comp_name, slot_key = key.rsplit(".", 1)

            # Inferred type check
            types_observed = set()
            examples = set()
            is_collection = False
            is_sensitive = is_probably_sensitive(slot_key)
            routes = set()

            for ev in events:
                nv = ev["new_value"]
                if nv is not None:
                    types_observed.add(type(nv).__name__)
                    if isinstance(nv, (list, dict)):
                        is_collection = True
                    # Only collect examples if not sensitive
                    if not is_sensitive:
                        examples.add(str(nv))
                if ev["route"]:
                    routes.add(ev["route"])

            # Derived check: always changed with at least one other slot on the same component
            is_derived = True
            for ev in events:
                sid = ev["session_id"]
                ts = ev["timestamp"]
                # Find all changes on same component in same session
                all_ts = comp_changes_by_session.get(sid, {}).get(comp_name, [])
                # Count changes at the exact same timestamp (tolerance within 50ms)
                co_changes = [t for t in all_ts if abs(t - ts) <= 0.05]
                if len(co_changes) <= 1:
                    is_derived = False
                    break

            inferred_type = "/".join(sorted(types_observed)) if types_observed else "any"
            observed_examples = list(examples)[:10]

            # Volatility check: average change count per session > 10
            change_count = len(events)
            sessions_active = len(set(ev["session_id"] for ev in events))
            frequency = change_count / sessions_active if sessions_active > 0 else 0
            is_volatile = frequency > 10

            desc_draft = f"Tracks the {slot_key} state for {comp_name}. Observed values: {', '.join(observed_examples[:3])}"

            annotations[key] = {
                "inferred_type": inferred_type,
                "observed_value_examples": observed_examples,
                "is_collection": is_collection,
                "is_probably_sensitive": is_sensitive,
                "is_derived": is_derived,
                "is_volatile": is_volatile,
                "is_readonly_annotated": False,  # Updated from registry description if matched
                "change_frequency_per_session": frequency,
                "description_draft": desc_draft,
                "routes_observed_on": sorted(routes),
                "confidence": min(1.0, 0.2 + 0.1 * len(events))
            }

        return annotations
