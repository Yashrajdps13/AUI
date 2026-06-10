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
    async def compile_goal(self, query: str, registry_snapshot: dict) -> Goal:
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

    async def compile_goal(self, query: str, registry_snapshot: dict) -> Goal:
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

        prompt = f"""
        Translate the following user natural language query into a structured Goal object with success and failure conditions, based on the current component registry state.
        
        User Query: "{query}"
        
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
        1. For success_conditions and failure_conditions, the "target" field MUST be chosen strictly from the "Allowed Target State Slots" list. Do NOT guess, invent, or use any target path that is not present in that list.
        2. You MUST use the exact strings from "Allowed Target State Slots" as the target in your conditions. For example, if the list contains "App#r9.attendeeName", use exactly "App#r9.attendeeName", NOT "App.attendeeName" or "PassesStore.pass_holder_name".
        3. If the user query explicitly mentions inputs, credentials, or values (e.g. "John Doe" or "john@test.com" or card "5555666677778888"), you MUST include success conditions verifying that the corresponding component UI state slots from the allowed list are updated to those expected values, in addition to the final outcome condition.
        
        CRITICAL RULES FOR FAILURE CONDITIONS:
        1. Failure conditions are evaluated at every single step, INCLUDING step 0 (before the agent has executed any actions).
        2. Do NOT include failure conditions that are True in the initial state, or that are simply the logical negations of the success conditions (e.g. if the success condition is 'token is truthy', do NOT set a failure condition of 'token is falsy', as it starts falsy and would fail the run immediately at step 0).
        3. Only use failure conditions to watch for explicit error messages, error state slots, or invalid state paths.
        4. If there are no clear error states or invalid conditions to monitor, leave "failure_conditions" as an empty list: [].
        
        Output strictly valid JSON only. Do not wrap in markdown blocks.
        """

        try:
            kwargs = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a structured compiler. Translate natural language queries into valid Goal JSON matching the schema."
                    },
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.0
            }
            if "ollama" not in self.model.lower():
                kwargs["response_format"] = {"type": "json_object"}

            response = await acompletion(**kwargs)

            import re
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
            
            # Map JSON to Goal object
            from react_agent_bridge.core.planner.goal import GoalCondition
            
            success_conds = []
            for cond in parsed.get("success_conditions", []):
                success_conds.append(GoalCondition(
                    target=cond["target"],
                    operator=cond["operator"],
                    value=cond.get("value")
                ))
                
            failure_conds = []
            for cond in parsed.get("failure_conditions", []):
                failure_conds.append(GoalCondition(
                    target=cond["target"],
                    operator=cond["operator"],
                    value=cond.get("value")
                ))
                
            return Goal(
                description=parsed.get("description", query),
                success_conditions=success_conds,
                failure_conditions=failure_conds,
                max_steps=parsed.get("max_steps", 15),
                timeout_seconds=parsed.get("timeout_seconds", 60.0)
            )

        except Exception as e:
            logger.error(f"LiteLLM compile_goal failed: {e}", exc_info=True)
            raise LLMError(f"LiteLLM failed to compile goal: {e}")
