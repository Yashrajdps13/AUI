import os
import re
import json
import logging
import urllib.request
import urllib.error
from typing import Optional, Callable, List
from react_agent_bridge.core.planner.goal import GoalCondition
from react_agent_bridge.business_logic.sections import BusinessLogicDoc, CompiledConstraint
from react_agent_bridge.core.rules.registry import RuleRegistry
from react_agent_bridge.core.rules.result import RuleViolation
from react_agent_bridge.core.graph.state_graph import ApplicationStateGraph
from react_agent_bridge.core.exceptions import ConstraintCompilationError

logger = logging.getLogger("react_agent_bridge.business_logic.compiler")


def make_rule_from_compiled_constraint(constraint: CompiledConstraint) -> Callable:
    """Generates a dynamic Python rule function from a CompiledConstraint."""
    def constraint_rule(command: dict, graph: ApplicationStateGraph) -> Optional[RuleViolation]:
        target = command.get("target", "")
        if not target:
            return None

        # Extract target component ID and action name (if applicable)
        cmd_type = command.get("type")
        if cmd_type in ["setState", "queryState"]:
            comp_id = target.rsplit(".", 1)[0] if "." in target else target
            action_name = None
        elif cmd_type == "callAction":
            parts = target.rsplit(".", 1)
            comp_id = parts[0] if len(parts) == 2 else target
            action_name = parts[1] if len(parts) == 2 else None
        else:
            comp_id = target
            action_name = None

        comp = graph.get_component(comp_id)
        display_name = comp.display_name if comp else comp_id

        # Check if this constraint targets the component
        matches_component = False
        for tc in constraint.target_components:
            if display_name == tc or comp_id == tc or comp_id.startswith(tc + "#") or comp_id.startswith(tc + ":"):
                matches_component = True
                break

        if not matches_component:
            return None

        # Check if this constraint specifies action filters
        if constraint.target_actions:
            if cmd_type != "callAction" or action_name not in constraint.target_actions:
                return None

        # Special check for read-only setState constraints
        if constraint.rule_type == "deny_always" and cmd_type == "setState" and "setState" in constraint.name.lower():
            return RuleViolation(
                rule_name=constraint.name,
                message=f"Constraint '{constraint.name}' violated: setState is not allowed on component '{comp_id}'.",
                target=target
            )

        if constraint.rule_type == "deny_always":
            return RuleViolation(
                rule_name=constraint.name,
                message=f"Constraint '{constraint.name}' violated: Action on '{comp_id}' is permanently denied.",
                target=target
            )

        if constraint.condition:
            satisfied = constraint.condition.evaluate(graph)

            if constraint.rule_type == "allow_if" and not satisfied:
                return RuleViolation(
                    rule_name=constraint.name,
                    message=(
                        f"Constraint '{constraint.name}' violated: Action on '{comp_id}' "
                        f"only allowed if '{constraint.condition.target} {constraint.condition.operator} {constraint.condition.value}'."
                    ),
                    target=target
                )
            elif constraint.rule_type == "deny_unless" and not satisfied:
                return RuleViolation(
                    rule_name=constraint.name,
                    message=(
                        f"Constraint '{constraint.name}' violated: Action on '{comp_id}' "
                        f"denied unless '{constraint.condition.target} {constraint.condition.operator} {constraint.condition.value}'."
                    ),
                    target=target
                )

        return None

    constraint_rule.__name__ = constraint.name
    return constraint_rule


def compile_with_openai_http(name: str, text: str, api_key: str) -> CompiledConstraint:
    """Uses a direct urllib POST request to OpenAI to compile a constraint using JSON mode."""
    url = "https://api.openai.com/v1/chat/completions"
    prompt = f"""
    You are an expert compiler. Translate the following plain English business constraint for an AI agent into a structured JSON representation matching the target schema.
    
    Constraint Name: {name}
    Constraint Text: {text}
    
    Target Schema:
    {{
      "name": "string (the constraint name)",
      "target_components": ["list of component display name prefixes affected"],
      "target_actions": ["optional list of action name strings affected, or empty list"],
      "condition": {{
         "target": "string (path to dependent state slot, e.g. 'AuthStore.isLoggedIn')",
         "operator": "equals | truthy | falsy | changed",
         "value": "any (value to check against for equals operator, e.g. true, 'admin', null)"
      }},
      "rule_type": "allow_if | deny_always | deny_unless"
    }}
    
    Output strictly valid JSON with no markdown block formatting.
    """
    
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "You are a structured compiler. Output JSON only."},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.0
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        },
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10.0) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            content = res_data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            
            cond = parsed.get("condition")
            condition_obj = None
            if cond and isinstance(cond, dict) and cond.get("target") and cond.get("operator"):
                condition_obj = GoalCondition(
                    target=cond["target"],
                    operator=cond["operator"],
                    value=cond.get("value")
                )
                
            return CompiledConstraint(
                name=parsed.get("name", name),
                target_components=parsed.get("target_components", []),
                target_actions=parsed.get("target_actions", []),
                condition=condition_obj,
                rule_type=parsed.get("rule_type", "allow_if")
            )
    except Exception as e:
        logger.error(f"OpenAI HTTP constraint compilation failed: {e}")
        raise ConstraintCompilationError(f"OpenAI failed to compile constraint '{name}': {e}")


def compile_with_fallback_regex(name: str, text: str) -> Optional[CompiledConstraint]:
    """Uses pattern matching to parse basic constraints locally without external API requirements."""
    # Pattern 1: Deny unless state condition met
    # e.g., "The agent must never call any action on PaymentStore unless AuthStore.userRole equals "admin""
    m1 = re.search(
        r"never\s+call\s+any\s+action\s+on\s+([A-Za-z0-9_]+)\s+unless\s+([A-Za-z0-9_\.]+)\s+(equals|==|is)\s+['\"]?([A-Za-z0-9_]+)['\"]?",
        text,
        re.IGNORECASE
    )
    if m1:
        comp, target_state, op, val = m1.groups()
        # Coerce operator
        op_coerce = "equals" if op in ["equals", "==", "is"] else op
        
        # Coerce value
        val_coerce = val
        if val.lower() == "true":
            val_coerce = True
        elif val.lower() == "false":
            val_coerce = False
        elif val.lower() in ["null", "nil", "none"]:
            val_coerce = None

        return CompiledConstraint(
            name=name,
            target_components=[comp],
            target_actions=[],
            condition=GoalCondition(target=target_state, operator=op_coerce, value=val_coerce),
            rule_type="deny_unless"
        )

    # Pattern 2: Deny unless boolean state condition met
    m2 = re.search(
        r"never\s+attempt\s+any\s+action\s+on\s+([A-Za-z0-9_]+)\s+unless\s+([A-Za-z0-9_\.]+)\s+equals\s+true",
        text,
        re.IGNORECASE
    )
    if m2:
        comp, target_state = m2.groups()
        return CompiledConstraint(
            name=name,
            target_components=[comp],
            target_actions=[],
            condition=GoalCondition(target=target_state, operator="equals", value=True),
            rule_type="deny_unless"
        )

    # Pattern 3: Read-only setState block
    # e.g., "never use setState on any slot of InventoryTable"
    m3 = re.search(
        r"never\s+use\s+setState\s+on\s+any\s+slot\s+of\s+([A-Za-z0-9_]+)",
        text,
        re.IGNORECASE
    )
    if m3:
        comp = m3.group(1)
        return CompiledConstraint(
            name=name,
            target_components=[comp],
            target_actions=[],
            condition=None,
            rule_type="deny_always"
        )

    return None


class BusinessLogicCompiler:
    """
    Compiles English constraints from the parsed document into Python rules in the RuleRegistry.
    """
    def __init__(self, llm_compiler: Optional[Callable[[str, str], CompiledConstraint]] = None):
        self.llm_compiler = llm_compiler

    def compile(self, doc: BusinessLogicDoc, registry: RuleRegistry):
        """Compiles constraints in doc and registers them into the rule registry."""
        compiled_list = []

        # Try to resolve compiler or fallbacks
        api_key = os.environ.get("OPENAI_API_KEY")

        for name, text in doc.constraints.items():
            compiled = None
            
            # 1. Try Custom Developer Compiler
            if self.llm_compiler:
                try:
                    compiled = self.llm_compiler(name, text)
                except Exception as e:
                    logger.error(f"Developer llm_compiler failed for '{name}': {e}")
                    raise ConstraintCompilationError(f"Failed to compile constraint '{name}': {e}")
            
            # 2. Try Fallback Regex parsing (offline/fast)
            if not compiled:
                compiled = compile_with_fallback_regex(name, text)

            # 3. Try OpenAI API call (if key is set)
            if not compiled and api_key:
                try:
                    compiled = compile_with_openai_http(name, text, api_key)
                except Exception as e:
                    logger.warning(f"OpenAI compilation failed for '{name}', raising error: {e}")
                    raise ConstraintCompilationError(f"Could not compile constraint '{name}': {e}")

            # 4. If all fail, raise compile error
            if not compiled:
                raise ConstraintCompilationError(
                    f"Could not compile constraint '{name}'. "
                    f"Please provide an llm_compiler function, set OPENAI_API_KEY, or write standard patterns."
                )

            compiled_list.append(compiled)
            
            # Translate compiled constraint to rule function and register it with HIGH priority (200)
            rule_fn = make_rule_from_compiled_constraint(compiled)
            registry.add_rule(rule_fn, priority=200)

        doc.compiled_constraints = compiled_list
        logger.info(f"Successfully compiled {len(compiled_list)} domain constraints.")
