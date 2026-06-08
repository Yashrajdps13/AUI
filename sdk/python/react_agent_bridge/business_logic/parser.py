import re
from typing import List, Optional, Tuple, Any
from react_agent_bridge.core.planner.goal import GoalCondition
from react_agent_bridge.business_logic.sections import (
    BusinessLogicDoc,
    GlossaryEntry,
    WorkflowDefinition
)


def parse_value(val_str: str) -> Any:
    """Coerces parsed string values into Python types (bool, int, float, str)."""
    val_str = val_str.strip()
    if val_str.lower() in ["true", "yes"]:
        return True
    if val_str.lower() in ["false", "no"]:
        return False
    if val_str.lower() in ["null", "none", "nil"]:
        return None
    
    # Try parsing as numeric
    if val_str.isdigit():
        return int(val_str)
    try:
        return float(val_str)
    except ValueError:
        pass

    # Strip surrounding quotes if present
    if (val_str.startswith('"') and val_str.endswith('"')) or (val_str.startswith("'") and val_str.endswith("'")):
        return val_str[1:-1]
        
    return val_str


def parse_goal_condition(line: str) -> Optional[GoalCondition]:
    """
    Parses a string condition line (e.g. 'AuthStore.isLoggedIn equals true')
    into a GoalCondition object.
    """
    cleaned = line.strip()
    # Strip list markers or prefixes
    cleaned = re.sub(r'^([-\*\+]|\d+\.)\s+', '', cleaned)
    cleaned = re.sub(r'^(Preconditions:|Success condition:|Failure condition:)\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()

    if not cleaned:
        return None

    # Supported operators: equals, truthy, falsy, changed
    if " equals " in cleaned:
        target, val_str = cleaned.split(" equals ", 1)
        return GoalCondition(target=target.strip(), operator="equals", value=parse_value(val_str))
    elif " == " in cleaned:
        target, val_str = cleaned.split(" == ", 1)
        return GoalCondition(target=target.strip(), operator="equals", value=parse_value(val_str))
    elif "is truthy" in cleaned or "truthy" in cleaned:
        target = cleaned.replace("is truthy", "").replace("truthy", "").strip()
        return GoalCondition(target=target, operator="truthy")
    elif "is falsy" in cleaned or "falsy" in cleaned:
        target = cleaned.replace("is falsy", "").replace("falsy", "").strip()
        return GoalCondition(target=target, operator="falsy")
    elif "is changed" in cleaned or "changed" in cleaned:
        target = cleaned.replace("is changed", "").replace("changed", "").strip()
        return GoalCondition(target=target, operator="changed")

    return None


def parse_routes(text: str) -> List[str]:
    """Extracts route patterns from matching glossary text descriptions."""
    routes = []
    # Search patterns: "routes matching `/checkout`" or "only on `/checkout`" or "route `/checkout`"
    matches = re.findall(r'(?:routes matching|only on|route)\s+`([^`]+)`', text, re.IGNORECASE)
    for m in matches:
        routes.append(m.strip())
    return routes


class BusinessLogicParser:
    """
    Parses raw Markdown documentation text into a structured BusinessLogicDoc.
    """
    @staticmethod
    def parse(markdown_text: str) -> BusinessLogicDoc:
        doc = BusinessLogicDoc()
        lines = markdown_text.splitlines()

        current_h2 = None
        current_h3 = None
        current_block_lines = []

        # Helper to process blocks when moving to the next heading or EOF
        def flush_block():
            nonlocal current_h2, current_h3, current_block_lines
            if not current_h2 or not current_h3:
                return

            block_text = "\n".join(current_block_lines).strip()
            
            if current_h2 == "## Component Glossary":
                routes = parse_routes(block_text)
                doc.glossary[current_h3] = GlossaryEntry(
                    component_name=current_h3,
                    description=block_text,
                    routes=routes
                )
            elif current_h2 == "## Workflow Definitions":
                preconditions = []
                steps = []
                success_cond = None
                failure_cond = None

                in_steps = False
                for line in current_block_lines:
                    line_strip = line.strip()
                    if not line_strip:
                        continue
                    
                    if line_strip.lower().startswith("preconditions:"):
                        in_steps = False
                        cond = parse_goal_condition(line_strip)
                        if cond:
                            preconditions.append(cond)
                        continue
                    
                    if line_strip.lower().startswith("steps:"):
                        in_steps = True
                        continue

                    if line_strip.lower().startswith("success condition:"):
                        in_steps = False
                        success_cond = parse_goal_condition(line_strip)
                        continue

                    if line_strip.lower().startswith("failure condition:"):
                        in_steps = False
                        failure_cond = parse_goal_condition(line_strip)
                        continue

                    # Parse step description or list condition
                    if in_steps:
                        # Strip number markers: "1. Click next" -> "Click next"
                        step_desc = re.sub(r'^\d+\.\s*', '', line_strip)
                        steps.append(step_desc)
                    else:
                        # If list item under preconditions, append
                        if line_strip.startswith("-") or line_strip.startswith("*"):
                            cond = parse_goal_condition(line_strip)
                            if cond:
                                preconditions.append(cond)

                doc.workflows[current_h3] = WorkflowDefinition(
                    name=current_h3,
                    preconditions=preconditions,
                    steps=steps,
                    success_condition=success_cond,
                    failure_condition=failure_cond
                )
            elif current_h2 == "## Constraints":
                doc.constraints[current_h3] = block_text

            current_block_lines = []

        for line in lines:
            line_strip = line.strip()
            
            # H2 Heading detection
            if line_strip.startswith("## ") and not line_strip.startswith("###"):
                flush_block()
                current_h2 = line_strip
                current_h3 = None
                continue
            
            # H3 Heading detection
            if line_strip.startswith("### "):
                flush_block()
                current_h3 = line_strip[4:].strip()
                current_block_lines = []
                continue

            # Gather text for the active H2/H3 section
            if current_h2 == "## Sensitive Context":
                doc.sensitive_context += line + "\n"
            elif current_h2 and current_h3:
                current_block_lines.append(line)

        # Flush any remaining block at end of file
        flush_block()
        doc.sensitive_context = doc.sensitive_context.strip()
        return doc
