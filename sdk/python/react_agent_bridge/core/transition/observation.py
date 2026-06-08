import time
from dataclasses import dataclass, field
from typing import List


@dataclass
class TransitionObservation:
    """
    Represents a point-in-time observation of a state transition caused by an agent command.
    """
    command: dict
    state_before: dict
    state_after: dict
    ack_success: bool
    slots_changed: List[str] = field(default_factory=list)
    time_to_settle_ms: float = 0.0
    session_id: str = ""
    timestamp: float = field(default_factory=time.time)
