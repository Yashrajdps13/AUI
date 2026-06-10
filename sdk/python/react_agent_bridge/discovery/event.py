from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, Literal


class DiscoveryEventType(str, Enum):
    COMPONENT_MOUNTED = "COMPONENT_MOUNTED"
    COMPONENT_UNMOUNTED = "COMPONENT_UNMOUNTED"
    SLOT_CHANGED = "SLOT_CHANGED"
    ACTION_CALLED = "ACTION_CALLED"
    INTERACTION_OCCURRED = "INTERACTION_OCCURRED"
    ROUTE_CHANGED = "ROUTE_CHANGED"
    RENDER_SETTLED = "RENDER_SETTLED"
    AGENT_COMMAND_DISPATCHED = "AGENT_COMMAND_DISPATCHED"
    AGENT_COMMAND_SUCCEEDED = "AGENT_COMMAND_SUCCEEDED"
    AGENT_COMMAND_FAILED = "AGENT_COMMAND_FAILED"
    WORKFLOW_COMPLETED = "WORKFLOW_COMPLETED"


@dataclass
class DiscoveryEvent:
    event_type: DiscoveryEventType
    timestamp: float  # Epoch timestamp in seconds
    session_id: str
    session_type: Literal["human", "agent"]
    component_id: Optional[str] = None
    component_display_name: Optional[str] = None
    slot_key: Optional[str] = None
    previous_value: Optional[Any] = None
    new_value: Optional[Any] = None
    change_source: Optional[Literal["user", "agent", "system"]] = None
    element_selector: Optional[str] = None
    route: Optional[str] = None
    settle_duration_ms: Optional[float] = None
    confidence: float = 1.0
