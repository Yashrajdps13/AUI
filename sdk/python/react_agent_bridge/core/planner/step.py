from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PlanStep:
    """
    Represents a single step executed during a planning loop.
    """
    step_index: int
    command: dict
    rule_check_passed: bool
    ack_success: bool
    post_condition_verified: bool
    time_taken_ms: float
    error_message: Optional[str] = None


@dataclass
class PlanResult:
    """
    Represents the final result of goal-directed execution.
    """
    success: bool
    steps_executed: int
    history: List[PlanStep] = field(default_factory=list)
    error_message: Optional[str] = None
