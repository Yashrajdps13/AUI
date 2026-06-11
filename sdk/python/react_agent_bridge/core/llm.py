import os
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
from react_agent_bridge.core.planner.goal import Goal
from react_agent_bridge.core.exceptions import BridgeError

logger = logging.getLogger("react_agent_bridge.llm")


@dataclass
class StructuredAction:
    """
    Represents a structured action/command decided by the LLM.
    """
    name: str
    arguments: dict


class LLMError(BridgeError):
    """
    Raised when an LLM provider call fails or returns invalid outputs.
    """
    pass


class BaseLLMAdapter(ABC):
    """
    Abstract base class defining the standard interface for LLM adapter integrations.
    """
    @abstractmethod
    async def call(self, prompt: str, tools: list, goal: Goal) -> StructuredAction:
        """
        Sends the prompt and planning tools to the LLM, returning a StructuredAction.
        """
        pass

    @abstractmethod
    async def compile_goal(self, query: str, registry_snapshot: dict, original_query: Optional[str] = None) -> Goal:
        """
        Translates a natural language query into a structured Goal object.
        """
        pass


class LiteLLMAdapter(BaseLLMAdapter):
    """
    Concrete implementation of BaseLLMAdapter using the LiteLLM library.
    Defaults to the ollama/qwen2.5:7b model.
    """
    def __init__(self, model: str = "ollama/qwen2.5:7b"):
        self.model = model

    async def call(self, prompt: str, tools: list, goal: Goal) -> StructuredAction:
        try:
            import litellm
            from litellm import acompletion
        except ImportError:
            raise ImportError(
                "litellm is required to use LiteLLMAdapter. "
                "Please install it using: pip install litellm"
            )

        # Sync API keys from local environment variables
        gemini_key = os.environ.get("GEMINI_API_KEY")
        litellm_key = os.environ.get("LITELLM_API_KEY")

        if gemini_key:
            os.environ["GEMINI_API_KEY"] = gemini_key
        if litellm_key:
            os.environ["LITELLM_API_KEY"] = litellm_key

        if not gemini_key and not litellm_key and "gemini" in self.model:
            raise LLMError("Neither GEMINI_API_KEY nor LITELLM_API_KEY environment variable is set.")

        try:
            logger.debug(f"Sending prompt to LiteLLM model {self.model}")
            
            is_ollama = "ollama" in self.model.lower()
            if is_ollama:
                # Bypass LiteLLM tool calling parser for Ollama to prevent KeyError: 'name' crashes
                tools_desc = []
                for tool in tools:
                    func = tool["function"]
                    tools_desc.append(
                        f"- **{func['name']}**: {func['description']}\n"
                        f"  Parameters schema:\n"
                        f"  {json.dumps(func['parameters'], indent=4)}"
                    )
                tools_str = "\n\n".join(tools_desc)

                ollama_prompt = f"""
{prompt}

You MUST select exactly ONE of the following tools to progress towards the goal:

{tools_str}

Output your decision as a valid JSON object matching the schema below:
{{
    "tool_name": "name_of_selected_tool",
    "arguments": {{
        "param_name": "param_value"
    }}
}}

Ensure the arguments match the parameters schema of the selected tool.
Output strictly valid JSON only. Do not wrap in markdown blocks or include explanations.
"""
                response = await acompletion(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a planning coordinator. You MUST choose one of the available tools to progress towards the goal."
                        },
                        {"role": "user", "content": ollama_prompt}
                    ],
                    temperature=0.0
                )
                
                raw_content = response.choices[0].message.content
                if not raw_content:
                    raise LLMError("Model returned an empty response.")
                
                content = raw_content.strip()
                import re
                match_json = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
                if match_json:
                    content = match_json.group(1).strip()
                else:
                    match_block = re.search(r"```\s*(.*?)\s*```", content, re.DOTALL)
                    if match_block:
                        content = match_block.group(1).strip()
                    else:
                        start = content.find("{")
                        end = content.rfind("}")
                        if start != -1 and end != -1 and end > start:
                            content = content[start:end+1].strip()
                            
                parsed = json.loads(content)
                name = parsed["tool_name"]
                arguments = parsed["arguments"]
                logger.debug(f"LiteLLM selected tool {name} with args {arguments}")
                return StructuredAction(name=name, arguments=arguments)

            else:
                response = await acompletion(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a planning coordinator. You MUST choose one of the available tools to progress towards the goal."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    tools=tools,
                    tool_choice="required",
                    temperature=0.0
                )

                message = response.choices[0].message
                if hasattr(message, "tool_calls") and message.tool_calls:
                    tool_call = message.tool_calls[0]
                    name = tool_call.function.name
                    
                    # Parse arguments safely
                    args_str = tool_call.function.arguments
                    if isinstance(args_str, str):
                        arguments = json.loads(args_str)
                    else:
                        arguments = args_str
                        
                    logger.debug(f"LiteLLM selected tool {name} with args {arguments}")
                    return StructuredAction(name=name, arguments=arguments)

                raise LLMError("LiteLLM response did not contain any valid tool calls.")

        except Exception as e:
            if isinstance(e, LLMError):
                raise
            logger.error(f"LiteLLM completion call failed: {e}", exc_info=True)
            raise LLMError(f"LiteLLM call failed: {e}")

    async def compile_goal(self, query: str, registry_snapshot: dict, original_query: Optional[str] = None) -> Goal:
        try:
            import litellm
            from litellm import acompletion
        except ImportError:
            raise ImportError(
                "litellm is required to use LiteLLMAdapter. "
                "Please install it using: pip install litellm"
            )

        gemini_key = os.environ.get("GEMINI_API_KEY")
        litellm_key = os.environ.get("LITELLM_API_KEY")

        if gemini_key:
            os.environ["GEMINI_API_KEY"] = gemini_key
        if litellm_key:
            os.environ["LITELLM_API_KEY"] = litellm_key

        if not gemini_key and not litellm_key and "gemini" in self.model:
            raise LLMError("Neither GEMINI_API_KEY nor LITELLM_API_KEY environment variable is set.")

        # Extract allowed target state slots dynamically to prevent hallucination
        allowed_targets = []
        comps = registry_snapshot.get("components", registry_snapshot) if isinstance(registry_snapshot, dict) else {}
        for comp_id, comp_data in comps.items():
            if isinstance(comp_data, dict) and "stateSlots" in comp_data:
                for slot_key in comp_data["stateSlots"].keys():
                    allowed_targets.append(f"{comp_id}.{slot_key}")

        def get_clean_parts(cid: str) -> set:
            import re
            parts = set(re.split(r'[^a-zA-Z0-9]', cid))
            cleaned = set()
            for p in parts:
                if not p:
                    continue
                if p.isdigit():
                    continue
                if re.match(r'^r\d+$', p, re.IGNORECASE):
                    continue
                cleaned.add(p)
            return cleaned

        def is_valid_target(t_name: str, allowed: List[str]) -> bool:
            if not allowed:
                return True
            if t_name.endswith(".isMounted") or t_name.endswith(".route"):
                return True
            if t_name in allowed:
                return True
            
            parts = t_name.split(".", 1)
            if len(parts) != 2:
                return False
            comp_id, path_str = parts
            
            import re
            segments = path_str.split(".")
            first_segment = segments[0]
            match_bracket = re.match(r'^([^\[]+)(.*)$', first_segment)
            slot_key = match_bracket.group(1) if match_bracket else first_segment
            
            target_parts = get_clean_parts(comp_id)
            
            for a in allowed:
                a_parts = a.split(".", 1)
                if len(a_parts) != 2:
                    continue
                a_comp_id, a_slot_key = a_parts
                if slot_key == a_slot_key:
                    allowed_parts = get_clean_parts(a_comp_id)
                    if target_parts.intersection(allowed_parts):
                        return True
            return False

        original_query_str = f'\n        Original Context Query (for context / resolving pronouns only): "{original_query}"' if original_query else ""
        prompt = f"""
        Translate the following user natural language query (User Query) into a structured Goal object with success and failure conditions, based on the current component registry state.
        
        User Query: "{query}"{original_query_str}
        
        Active Registry Snapshot:
        {json.dumps(registry_snapshot, indent=2)}
        
        Allowed Target State Slots:
        {json.dumps(allowed_targets, indent=2)}
        
        Goal JSON Schema:
        {{
            "description": "Natural language description of the goal",
            "success_conditions": [
                {{
                    "target": "The exact target slot chosen strictly from the 'Allowed Target State Slots' list.",
                    "operator": "equals | truthy | falsy | changed",
                    "value": "optional value to match if operator is equals, e.g. true, 'admin', null"
                }}
            ],
            "failure_conditions": [
                {{
                    "target": "The exact target slot chosen strictly from the 'Allowed Target State Slots' list.",
                    "operator": "equals | truthy | falsy | changed",
                    "value": "optional value"
                }}
            ],
            "max_steps": 15,
            "timeout_seconds": 60.0
        }}
        
        CRITICAL RULES FOR GOAL COMPILATION:
        1. NEVER USE ERROR STATE SLOTS (such as target names ending with '.error' or containing 'error', e.g. 'LoginView.error' or 'LoginView#r5.error' being empty/null) OR DEBUG/CONSOLE LOGS (such as 'consoleLogs', 'appLog', 'logs') AS SUCCESS CONDITIONS. The absence of an error state or a log change is NOT a success signal and MUST be rejected. Instead, look for a positive outcome state in Zustand global stores or primary state slots (such as 'AuthStore.isAuthenticated' being true, or 'AuthStore.isLoggedIn' being true, or user details populated).
        2. For success_conditions and failure_conditions, the "target" field MUST be chosen strictly from the "Allowed Target State Slots" list. Do NOT guess, invent, or use any target path that is not present in that list.
        3. You MUST use the exact strings from "Allowed Target State Slots" as the target in your conditions. For example, if the list contains "App#r9.attendeeName", use exactly "App#r9.attendeeName", NOT "App.attendeeName" or "PassesStore.pass_holder_name".
        4. Do NOT include temporary input values or intermediate form fields (such as login password, search query, or form inputs) in the success_conditions if the user moves beyond that step or if the form/component unmounts or is reset. Instead, focus success conditions on final persistent state outcomes (e.g. user being authenticated in the AuthStore/Layout component, project list including the new project, task marked complete). Only include input values in success conditions if the goal is explicitly just to type a value and verify it remains visible on the current un-navigated screen.
        5. For navigation, routing, or page-transition goals where a target component/view is not yet mounted (and therefore its slots are missing from the registry snapshot), you MUST use virtual slots to check if the target component is mounted or the route is updated. Virtual slots use the target format:
           - ComponentName.isMounted: equals true/false (use when the goal is to load/navigate to a component/page)
           - ComponentName.route: equals "/path/to/route" (use when checking the current route)
           Example: if navigating to a ProjectDetailView, set target: "ProjectDetailView.isMounted", operator: "equals", value: true.
        6. You MUST only compile success conditions for the actions described in the "User Query". The "Original Context Query" is provided strictly as background context to help you resolve pronouns (like "its", "that", "this") or references. Do NOT compile success conditions for parts of the "Original Context Query" that are not requested in the "User Query".
        7. For goals that request incrementing or decrementing a numeric value or counter by a specific amount (e.g. "increment the counter three times"), you MUST compute the target value based on the current value in the registry snapshot (e.g. current + 3), and compile a success condition using the "equals" operator targeting that exact value (e.g. target: "ReduxStore#redux.counter.value", operator: "equals", value: 3). DO NOT use the "changed" operator for counters or numeric values if a specific target value can be computed.
        
        CRITICAL RULES FOR FAILURE CONDITIONS:
        1. Failure conditions are evaluated at every single step, INCLUDING step 0 (before the agent has executed any actions).
        2. Do NOT include failure conditions that are True in the initial state, or that are simply the logical negations of the success conditions (e.g. if the success condition is 'token is truthy', do NOT set a failure condition of 'token is falsy', as it starts falsy and would fail the run immediately at step 0).
        3. Only use failure conditions to watch for explicit error messages, error state slots, or invalid state paths.
        4. If there are no clear error states or invalid conditions to monitor, leave "failure_conditions" as an empty list: [].
        
        Output strictly valid JSON only. Do not wrap in markdown blocks.
        """

        import re
        from react_agent_bridge.core.planner.goal import GoalCondition

        max_attempts = 3
        current_attempt = 1
        system_prompt = "You are a structured compiler. Translate natural language queries into valid Goal JSON matching the schema."
        user_prompt = prompt

        while current_attempt <= max_attempts:
            try:
                kwargs = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.0
                }
                if "ollama" not in self.model.lower():
                    kwargs["response_format"] = {"type": "json_object"}

                response = await acompletion(**kwargs)
                raw_content = response.choices[0].message.content
                if not raw_content:
                    raise LLMError("Model returned an empty response.")

                content = raw_content.strip()
                # 1. Try to extract JSON from ```json ... ``` block
                match_json = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
                if match_json:
                    content = match_json.group(1).strip()
                else:
                    # 2. Try to extract JSON from generic ``` ... ``` block
                    match_block = re.search(r"```\s*(.*?)\s*```", content, re.DOTALL)
                    if match_block:
                        content = match_block.group(1).strip()
                    else:
                        # 3. Fallback: extract substring between the first '{' and last '}'
                        start = content.find("{")
                        end = content.rfind("}")
                        if start != -1 and end != -1 and end > start:
                            content = content[start:end+1].strip()

                parsed = json.loads(content)
                
                success_conds = []
                failure_conds = []
                invalid_targets = []
                
                for cond in parsed.get("success_conditions", []):
                    t = cond["target"]
                    t_lower = t.lower()
                    if any(x in t_lower for x in ["error", "consolelogs", "applog", "logs"]):
                        invalid_targets.append(t)
                    elif not is_valid_target(t, allowed_targets):
                        invalid_targets.append(t)
                    else:
                        success_conds.append(GoalCondition(
                            target=t,
                            operator=cond["operator"],
                            value=cond.get("value")
                        ))

                for cond in parsed.get("failure_conditions", []):
                    t = cond["target"]
                    t_lower = t.lower()
                    if not is_valid_target(t, allowed_targets):
                        invalid_targets.append(t)
                    else:
                        failure_conds.append(GoalCondition(
                            target=t,
                            operator=cond["operator"],
                            value=cond.get("value")
                        ))

                if invalid_targets:
                    feedback_msg = f"Your compiled goal included invalid targets: {invalid_targets}. " \
                                   f"CRITICAL RULE: You MUST choose targets strictly from the 'Allowed Target State Slots' list, " \
                                   f"or use virtual slots (e.g. 'ComponentName.isMounted' or 'ComponentName.route') for navigation/routing. " \
                                   f"No other target names or paths are allowed."
                    logger.warning(f"compile_goal attempt {current_attempt} failed: invalid targets {invalid_targets}. Retrying...")
                    user_prompt = f"{prompt}\n\n[Correction Feedback from previous attempt]:\n{feedback_msg}"
                    current_attempt += 1
                    continue

                if not success_conds:
                    feedback_msg = "Your compiled goal contains no success conditions. You must provide at least one success condition targeting a positive outcome state."
                    logger.warning(f"compile_goal attempt {current_attempt} failed: no success conditions. Retrying...")
                    user_prompt = f"{prompt}\n\n[Correction Feedback from previous attempt]:\n{feedback_msg}"
                    current_attempt += 1
                    continue
                    
                return Goal(
                    description=parsed.get("description", query),
                    success_conditions=success_conds,
                    failure_conditions=failure_conds,
                    max_steps=parsed.get("max_steps", 15),
                    timeout_seconds=parsed.get("timeout_seconds", 60.0)
                )

            except Exception as e:
                if current_attempt == max_attempts:
                    logger.error(f"LiteLLM compile_goal failed after {max_attempts} attempts: {e}", exc_info=True)
                    raise LLMError(f"LiteLLM failed to compile goal: {e}")
                logger.warning(f"compile_goal attempt {current_attempt} failed with error: {e}. Retrying...")
                current_attempt += 1
