from dataclasses import dataclass, field
from typing import List


@dataclass
class RuleViolation:
    """
    Represents a single rule violation during pre-flight gate checks.
    """
    rule_name: str
    message: str
    target: str
    details: dict = field(default_factory=dict)


@dataclass
class RuleResult:
    """
    Represents the output of evaluating a proposed action.
    """
    valid: bool
    violations: List[RuleViolation] = field(default_factory=list)
