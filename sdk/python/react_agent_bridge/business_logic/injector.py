from dataclasses import dataclass, field
from typing import List, Optional
from react_agent_bridge.business_logic.sections import (
    BusinessLogicDoc,
    GlossaryEntry,
    WorkflowDefinition
)
from react_agent_bridge.core.planner.goal import Goal


@dataclass
class BusinessLogicContext:
    """
    Holds the route and goal-filtered domain context injected into the prompt.
    """
    glossary: List[GlossaryEntry] = field(default_factory=list)
    workflows: List[WorkflowDefinition] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    sensitive_context: str = ""


class BusinessLogicInjector:
    """
    Selects relevant subsets of the BusinessLogicDoc for a given route and goal.
    """
    @staticmethod
    def select(
        doc: BusinessLogicDoc,
        route: Optional[str],
        goal: Optional[Goal],
        graph_snapshot: dict
    ) -> BusinessLogicContext:
        context = BusinessLogicContext()

        # 1. Filter Glossary
        # Retrieve mounted components display names
        mounted_names = set()
        components = graph_snapshot.get("components", {})
        for comp_data in components.values():
            if comp_data.get("displayName"):
                mounted_names.add(comp_data["displayName"])

        for entry in doc.glossary.values():
            route_match = False
            if route and entry.routes:
                for r in entry.routes:
                    if r == route or route.startswith(r):
                        route_match = True
                        break
            
            # Keep if no routes specified, matches current route, or component is in the snapshot
            if not entry.routes or route_match or entry.component_name in mounted_names:
                context.glossary.append(entry)

        # 2. Filter Workflows
        # Include workflows matching the goal description
        if goal:
            goal_desc = goal.description.lower()
            for wf in doc.workflows.values():
                if wf.name.lower() in goal_desc or goal_desc in wf.name.lower():
                    context.workflows.append(wf)

        # 3. Include Constraints (plain English summary)
        for name, text in doc.constraints.items():
            context.constraints.append(f"{name}: {text}")

        # 4. Sensitive Context (stripped from logs, but injected in prompt)
        context.sensitive_context = doc.sensitive_context

        return context
