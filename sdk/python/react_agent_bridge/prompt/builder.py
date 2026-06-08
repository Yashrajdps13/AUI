from typing import Optional
from react_agent_bridge.prompt.core import CORE_SYSTEM_PROMPT
from react_agent_bridge.prompt.formatters import format_graph_snapshot
from react_agent_bridge.business_logic.injector import BusinessLogicContext
from react_agent_bridge.core.planner.goal import Goal


def build_prompt(
    business_context: Optional[BusinessLogicContext],
    graph_snapshot: dict,
    goal: Optional[Goal] = None,
    log_safe: bool = False
) -> str:
    """
    Assembles the complete system prompt for the planning LLM.
    If log_safe is True, it strips any sensitive business context from the output.
    """
    sections = [CORE_SYSTEM_PROMPT]

    # Add Goal Context if available
    if goal:
        sections.append(f"## Current Objective\n{goal.description}")

    # Add Business Logic Context if available
    if business_context:
        sections.append("## Business Logic Context & Rules")
        
        # 1. Glossary
        if business_context.glossary:
            glossary_lines = ["### Component Roles & Glossary:"]
            for entry in business_context.glossary:
                routes_str = f" [Routes: {', '.join(entry.routes)}]" if entry.routes else ""
                glossary_lines.append(f"- **{entry.component_name}**: {entry.description}{routes_str}")
            sections.append("\n".join(glossary_lines))

        # 2. Workflows
        if business_context.workflows:
            workflow_lines = ["### Target Workflows:"]
            for wf in business_context.workflows:
                workflow_lines.append(f"- **Workflow**: {wf.name}")
                if wf.steps:
                    workflow_lines.append("  Steps:")
                    for i, step in enumerate(wf.steps):
                        workflow_lines.append(f"    {i+1}. {step}")
            sections.append("\n".join(workflow_lines))

        # 3. Constraints (English summaries)
        if business_context.constraints:
            constraint_lines = ["### Safety Constraints (Enforced):"]
            for constraint in business_context.constraints:
                constraint_lines.append(f"- {constraint}")
            sections.append("\n".join(constraint_lines))

        # 4. Sensitive Context (only if NOT compiling a log-safe version)
        if business_context.sensitive_context and not log_safe:
            sections.append(f"### Sensitive Operational Context:\n{business_context.sensitive_context}")

    # Add Live State Graph Context
    sections.append("## Live Application State Graph")
    sections.append(format_graph_snapshot(graph_snapshot))

    return "\n\n".join(sections)
