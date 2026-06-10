import time
import uuid
import logging
import hashlib
import json
from typing import Dict, Any, Optional, List
from react_agent_bridge.discovery.event import DiscoveryEvent, DiscoveryEventType

logger = logging.getLogger("react_agent_bridge.discovery.recorder")

SENSITIVE_KEYWORDS = {
    "password", "passwd", "pwd", "card", "cvv", "cvc", "ssn",
    "ssid", "secret", "token", "key", "email", "phone", "tel",
    "mobile", "dob", "birthdate", "account", "routing", "iban", "pin"
}


def is_probably_sensitive(slot_key: str) -> bool:
    slot_lower = slot_key.lower()
    return any(kw in slot_lower for kw in SENSITIVE_KEYWORDS)


class HumanSessionRecorder:
    """
    Observes all inbound WebSocket bridge messages during human or agent sessions
    and writes DiscoveryEvents to the corpus.
    """
    def __init__(self, bridge, corpus, session_type: str = "human"):
        self.bridge = bridge
        self.corpus = corpus
        self.session_type = session_type
        self.session_id = str(uuid.uuid4())
        self.started_at = time.time()
        self.current_route: Optional[str] = None
        self.last_slot_changed_time: float = time.time()
        self.active_components: Dict[str, dict] = {}
        self.last_interaction: Optional[Dict[str, Any]] = None  # Tracks latest click/interaction
        self.is_active = True

        # Generate version hash based on initial mounted component names if available
        self.app_version_hash = "initial_v1"

    async def start(self):
        # Determine application version hash from currently mounted components if any
        mounted = self.bridge.graph.get_mounted_components()
        if mounted:
            names = sorted([c.display_name for c in mounted])
            self.app_version_hash = hashlib.md5(json.dumps(names).encode("utf-8")).hexdigest()[:16]

        # Check for version changes and log a warning
        try:
            sessions = await self.corpus.get_sessions()
            if sessions:
                latest_session = sessions[-1]
                prev_version = latest_session.get("application_version_hash")
                if prev_version and prev_version != self.app_version_hash:
                    logger.warning(
                        f"Application version hash changed from {prev_version} to {self.app_version_hash}. "
                        "Older sessions will be down-weighted in future inferences."
                    )
        except Exception as e:
            logger.error(f"Failed to query previous sessions for version change detection: {e}")

        await self.corpus.start_session(
            session_id=self.session_id,
            session_type=self.session_type,
            started_at=self.started_at,
            app_version_hash=self.app_version_hash
        )

    async def stop(self, is_complete: bool = True):
        self.is_active = False
        await self.corpus.end_session(
            session_id=self.session_id,
            ended_at=time.time(),
            is_complete=is_complete
        )

    def _redact_if_sensitive(self, slot_key: str, val: Any) -> Any:
        if val is None:
            return None
        if is_probably_sensitive(slot_key):
            return "[REDACTED]"
        return val

    def _infer_selector_for_slot(self, comp_id: str, slot_key: str, val: Any) -> Optional[str]:
        comp = self.active_components.get(comp_id)
        if not comp:
            # Try to get from bridge graph
            graph_comp = self.bridge.graph.get_component(comp_id)
            if graph_comp:
                comp = {
                    "interactiveElements": [
                        {
                            "selector": el.selector,
                            "tagName": el.tagName,
                            "text": el.text,
                            "disabled": el.disabled,
                            "visible": el.visible
                        } for el in graph_comp.interactive_elements
                    ]
                }
        if not comp:
            return None

        elements = comp.get("interactiveElements", [])
        # 1. Search for matching input field selectors
        for el in elements:
            sel = el.get("selector", "")
            if slot_key.lower() in sel.lower():
                return sel

        # 2. Search for buttons if boolean transition
        if isinstance(val, bool):
            for el in elements:
                sel = el.get("selector", "")
                if "btn" in sel.lower() or "button" in el.get("tagName", "").lower():
                    return sel

        # 3. Fallback to first input or first button
        for el in elements:
            sel = el.get("selector", "")
            if el.get("tagName") == "INPUT":
                return sel
        return None

    async def on_message(self, data: dict):
        if not self.is_active:
            return

        msg_type = data.get("type")
        now = time.time()

        if msg_type == "registryDelta":
            # Registry deltas
            added = data.get("added", [])
            removed = data.get("removed", [])
            updated = data.get("updated", [])

            for item in added:
                self.active_components[item["id"]] = item
                # Route changed detection
                if item.get("route") and item["route"] != self.current_route:
                    self.current_route = item["route"]
                    await self.corpus.record_event(DiscoveryEvent(
                        event_type=DiscoveryEventType.ROUTE_CHANGED,
                        timestamp=now,
                        session_id=self.session_id,
                        session_type=self.session_type,
                        route=self.current_route
                    ))

                await self.corpus.record_event(DiscoveryEvent(
                    event_type=DiscoveryEventType.COMPONENT_MOUNTED,
                    timestamp=now,
                    session_id=self.session_id,
                    session_type=self.session_type,
                    component_id=item["id"],
                    component_display_name=item["displayName"],
                    route=item.get("route")
                ))

            for item in updated:
                self.active_components[item["id"]] = item
                if item.get("route") and item["route"] != self.current_route:
                    self.current_route = item["route"]
                    await self.corpus.record_event(DiscoveryEvent(
                        event_type=DiscoveryEventType.ROUTE_CHANGED,
                        timestamp=now,
                        session_id=self.session_id,
                        session_type=self.session_type,
                        route=self.current_route
                    ))

            for comp_id in removed:
                comp = self.active_components.pop(comp_id, None)
                await self.corpus.record_event(DiscoveryEvent(
                    event_type=DiscoveryEventType.COMPONENT_UNMOUNTED,
                    timestamp=now,
                    session_id=self.session_id,
                    session_type=self.session_type,
                    component_id=comp_id,
                    component_display_name=comp.get("displayName") if comp else None
                ))

        elif msg_type == "stateSnapshot":
            target = data.get("target")
            val = data.get("value")
            if not target:
                return

            parts = target.rsplit(".", 1)
            if len(parts) == 2:
                comp_id, slot_key = parts
            else:
                return

            comp = self.active_components.get(comp_id)
            comp_display_name = comp.get("displayName") if comp else comp_id

            previous_val = self.bridge.graph.get_slot_value(target)

            # Redact if sensitive
            redacted_prev = self._redact_if_sensitive(slot_key, previous_val)
            redacted_new = self._redact_if_sensitive(slot_key, val)

            # Check change source
            change_source = "system"
            if self.session_type == "agent":
                # In agent sessions, check if command is in flight
                change_source = "agent"
            else:
                # In human sessions, attribute to user
                change_source = "user"

            # If user session and change source is user, infer interaction
            if self.session_type == "human" and change_source == "user":
                inferred_selector = self._infer_selector_for_slot(comp_id, slot_key, val)
                if inferred_selector:
                    await self.corpus.record_event(DiscoveryEvent(
                        event_type=DiscoveryEventType.INTERACTION_OCCURRED,
                        timestamp=now,
                        session_id=self.session_id,
                        session_type=self.session_type,
                        component_id=comp_id,
                        component_display_name=comp_display_name,
                        element_selector=inferred_selector,
                        route=self.current_route
                    ))

            self.last_slot_changed_time = now

            await self.corpus.record_event(DiscoveryEvent(
                event_type=DiscoveryEventType.SLOT_CHANGED,
                timestamp=now,
                session_id=self.session_id,
                session_type=self.session_type,
                component_id=comp_id,
                component_display_name=comp_display_name,
                slot_key=slot_key,
                previous_value=redacted_prev,
                new_value=redacted_new,
                change_source=change_source,
                route=self.current_route
            ))

        elif msg_type == "renderSettled":
            settle_dur = (now - self.last_slot_changed_time) * 1000.0
            await self.corpus.record_event(DiscoveryEvent(
                event_type=DiscoveryEventType.RENDER_SETTLED,
                timestamp=now,
                session_id=self.session_id,
                session_type=self.session_type,
                component_id=data.get("target"),
                settle_duration_ms=settle_dur,
                route=self.current_route
            ))

        elif msg_type == "commandAck":
            cmd_id = data.get("commandId")
            success = data.get("success", False)
            ev_type = DiscoveryEventType.AGENT_COMMAND_SUCCEEDED if success else DiscoveryEventType.AGENT_COMMAND_FAILED
            await self.corpus.record_event(DiscoveryEvent(
                event_type=ev_type,
                timestamp=now,
                session_id=self.session_id,
                session_type=self.session_type,
                element_selector=cmd_id
            ))

        elif msg_type == "interaction":
            comp_id = data.get("componentId")
            event = data.get("event")
            selector = data.get("selector")
            comp = self.active_components.get(comp_id)
            comp_display_name = comp.get("displayName") if comp else comp_id
            
            await self.corpus.record_event(DiscoveryEvent(
                event_type=DiscoveryEventType.INTERACTION_OCCURRED,
                timestamp=now,
                session_id=self.session_id,
                session_type=self.session_type,
                component_id=comp_id,
                component_display_name=comp_display_name,
                element_selector=selector,
                route=self.current_route
            ))
