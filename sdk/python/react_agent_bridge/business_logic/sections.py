from dataclasses import dataclass, field
from typing import List, Dict, Optional
from react_agent_bridge.core.planner.goal import GoalCondition


@dataclass
class GlossaryEntry:
    """
    Glossary entry representing component roles and route constraints.
    """
    component_name: str
    description: str
    routes: List[str] = field(default_factory=list)


@dataclass
class WorkflowDefinition:
    """
    Predefined workflow representing state-based preconditions and steps.
    """
    name: str
    preconditions: List[GoalCondition] = field(default_factory=list)
    steps: List[str] = field(default_factory=list)
    success_condition: Optional[GoalCondition] = None
    failure_condition: Optional[GoalCondition] = None


@dataclass
class CompiledConstraint:
    """
    Structure representing a compiled safety rule.
    """
    name: str
    target_components: List[str]
    target_actions: List[str] = field(default_factory=list)
    condition: Optional[GoalCondition] = None
    rule_type: str = "allow_if"  # "allow_if" | "deny_always" | "deny_unless"


@dataclass
class BusinessLogicDoc:
    """
    Represents the parsed domain knowledge base compiled from Markdown files.
    """
    glossary: Dict[str, GlossaryEntry] = field(default_factory=dict)
    workflows: Dict[str, WorkflowDefinition] = field(default_factory=dict)
    constraints: Dict[str, str] = field(default_factory=dict)  # name -> description
    compiled_constraints: List[CompiledConstraint] = field(default_factory=list)
    sensitive_context: str = ""
