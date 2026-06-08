import time
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from react_agent_bridge.core.models import InteractiveElement


@dataclass
class SlotNode:
    key: str
    hook_index: int
    description: Optional[str] = None
    sensitive: bool = False
    value: Any = None
    previous_value: Any = None
    last_changed_at: float = 0.0
    value_history: List[Any] = field(default_factory=list)
    changed_by_agent: bool = False

    def update_value(self, new_value: Any, by_agent: bool = False, history_depth: int = 10):
        """Updates the state slot value, saving the old value to history."""
        if self.value != new_value:
            self.previous_value = self.value
            self.value = new_value
            self.last_changed_at = time.time()
            self.changed_by_agent = by_agent
            
            # Update history
            self.value_history.append(new_value)
            if len(self.value_history) > history_depth:
                self.value_history.pop(0)


@dataclass
class ComponentNode:
    id: str
    display_name: str
    mounted_at: int
    route: Optional[str] = None
    state_slots: Dict[str, SlotNode] = field(default_factory=dict)
    interactive_elements: List[InteractiveElement] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)

    # Runtime-derived metadata fields
    last_seen_at: float = field(default_factory=time.time)
    mount_count: int = 1
    parent_id: Optional[str] = None
    route_at_mount: Optional[str] = None
