import logging
import time
from typing import Dict, List, Any, Optional
from react_agent_bridge.core.graph.node import ComponentNode, SlotNode
from react_agent_bridge.core.graph.diff import GraphDiff
from react_agent_bridge.core.models import RegistryDeltaMessage

logger = logging.getLogger("react_agent_bridge.graph")


class ApplicationStateGraph:
    """
    Manages the application state graph reconstructed from React bridge updates.
    """
    def __init__(self):
        self.components: Dict[str, ComponentNode] = {}
        self.by_agent = False  # Track if a state change was agent-initiated

    def apply_delta(self, delta: RegistryDeltaMessage) -> GraphDiff:
        """
        Applies a registryDelta message to the graph.
        Returns a GraphDiff detailing added, updated, and removed components.
        """
        diff = GraphDiff()
        current_time = time.time()

        # 1. Process removed components
        for comp_id in delta.removed:
            if comp_id in self.components:
                self.components.pop(comp_id)
                diff.removed.append(comp_id)

        # 2. Process added and updated components
        parent_candidate = None
        for item in delta.added + delta.updated:
            is_new = item.id not in self.components
            
            # Reconstruct state slots
            slots = {}
            existing_comp = self.components.get(item.id)
            for s in item.stateSlots:
                # Retain existing value and history if component is being updated
                existing_slot = existing_comp.state_slots.get(s.key) if existing_comp else None
                if existing_slot:
                    slot_node = existing_slot
                    slot_node.description = s.description
                    slot_node.sensitive = s.sensitive or False
                    slot_node.writeable = s.writeable
                else:
                    slot_node = SlotNode(
                        key=s.key,
                        hook_index=s.hookIndex,
                        description=s.description,
                        sensitive=s.sensitive or False,
                        writeable=s.writeable,
                        value=None
                    )
                slots[s.key] = slot_node

            node = ComponentNode(
                id=item.id,
                display_name=item.displayName,
                mounted_at=item.mountedAt,
                route=item.route,
                state_slots=slots,
                interactive_elements=item.interactiveElements,
                actions=item.actions,
                last_seen_at=current_time
            )

            # Heuristic parent inference: if added at the same time and in order
            if is_new:
                if parent_candidate and abs(node.mounted_at - parent_candidate.mounted_at) < 50:
                    node.parent_id = parent_candidate.id
                parent_candidate = node
                node.route_at_mount = node.route
                self.components[node.id] = node
                diff.added.append(node)
            else:
                # Keep parent and mount metrics
                node.parent_id = existing_comp.parent_id
                node.mount_count = existing_comp.mount_count
                node.route_at_mount = existing_comp.route_at_mount
                self.components[node.id] = node
                diff.updated.append(node)

        return diff

    def update_state_value(self, target: str, value: Any):
        """
        Updates the value of a target state slot (e.g. 'ComponentId.slotKey').
        """
        parts = target.rsplit(".", 1)
        if len(parts) != 2:
            logger.warning(f"Invalid target path structure for state update: {target}")
            return
        
        comp_id, slot_key = parts
        comp = self.components.get(comp_id)
        if comp and slot_key in comp.state_slots:
            slot = comp.state_slots[slot_key]
            slot.update_value(value, by_agent=self.by_agent)
            logger.debug(f"State updated: {target} = {value} (by_agent={self.by_agent})")
        else:
            logger.debug(f"State update target not found in graph: {target}")

    def get_slot_value(self, target: str) -> Any:
        """Gets the value of a target slot."""
        parts = target.rsplit(".", 1)
        if len(parts) == 2:
            comp_id, slot_key = parts
            comp = self.components.get(comp_id)
            if comp and slot_key in comp.state_slots:
                return comp.state_slots[slot_key].value
        return None

    def get_component(self, comp_id: str) -> Optional[ComponentNode]:
        return self.components.get(comp_id)

    def get_mounted_components(self) -> List[ComponentNode]:
        return list(self.components.values())

    def get_writable_targets(self) -> List[str]:
        """Returns a list of target paths that can be written via setState."""
        targets = []
        for comp in self.components.values():
            for slot_key in comp.state_slots.keys():
                targets.append(f"{comp.id}.{slot_key}")
        return targets

    def get_reachable_actions(self) -> List[str]:
        """Returns a list of action target paths that can be called."""
        actions = []
        for comp in self.components.values():
            for action in comp.actions:
                actions.append(f"{comp.id}.{action}")
        return actions

    def get_interactive_elements(self) -> List[Dict[str, Any]]:
        """Returns all interactive elements across all mounted components."""
        elements = []
        for comp in self.components.values():
            for el in comp.interactive_elements:
                elements.append({
                    "componentId": comp.id,
                    "selector": el.selector,
                    "tagName": el.tagName,
                    "text": el.text,
                    "disabled": el.disabled,
                    "visible": el.visible
                })
        return elements

    def get_components_on_route(self, route: str) -> List[ComponentNode]:
        return [comp for comp in self.components.values() if comp.route == route]

    def is_slot_sensitive(self, target: str) -> bool:
        parts = target.rsplit(".", 1)
        if len(parts) == 2:
            comp_id, slot_key = parts
            comp = self.components.get(comp_id)
            if comp and slot_key in comp.state_slots:
                return comp.state_slots[slot_key].sensitive
        return False

    def snapshot(self) -> dict:
        """
        Returns a serializable dictionary snapshot of the current state graph.
        Redacts sensitive state values.
        """
        snap = {}
        for comp_id, comp in self.components.items():
            slots_snap = {}
            desc_snap = {}
            writeables_snap = {}
            for slot_key, slot in comp.state_slots.items():
                slots_snap[slot_key] = "[REDACTED]" if (slot.sensitive and slot.value) else slot.value
                if slot.description:
                    desc_snap[slot_key] = slot.description
                if getattr(slot, "writeable", None):
                    writeables_snap[slot_key] = slot.writeable
            
            snap[comp_id] = {
                "displayName": comp.display_name,
                "mountedAt": comp.mounted_at,
                "route": comp.route,
                "stateSlots": slots_snap,
                "stateSlotDescriptions": desc_snap,
                "stateSlotWriteables": writeables_snap,
                "interactiveElements": [
                    {
                        "selector": el.selector,
                        "tagName": el.tagName,
                        "text": el.text,
                        "disabled": el.disabled,
                        "visible": el.visible
                    } for el in comp.interactive_elements
                ],
                "actions": comp.actions,
                "parent_id": comp.parent_id
            }
        return {"components": snap, "timestamp": time.time()}

    def clear(self):
        self.components.clear()
