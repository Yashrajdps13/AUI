import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional, TypedDict

# Add local SDK path to sys.path before imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../sdk/python")))

import litellm
from react_agent_bridge import ReactAgentBridge, BridgeError, LiteLLMAdapter, Goal, GoalCondition
from langgraph.graph import StateGraph, END

# Suppress verbose LiteLLM and HTTPX logging
logging.getLogger("litellm").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Terminal text colors
RED = "\033[1;31m"
YELLOW = "\033[1;33m"
GREEN = "\033[1;32m"
CYAN = "\033[1;36m"
RESET = "\033[0m"

# Global configuration
PLANNER_MODEL = os.environ.get("PLANNER_MODEL", "ollama/qwen2.5:7b")
CONSECUTIVE_INEFFECTIVE_LIMIT = 2

# Initialize bridge server on port 8000
adapter = LiteLLMAdapter(model=PLANNER_MODEL)
bridge = ReactAgentBridge(host="localhost", port=8000, llm_adapter=adapter)


def on_connect():
    print(f"\n{GREEN}[Bridge Connected] React application successfully linked!{RESET}")


def on_disconnect():
    print(f"\n{YELLOW}[Bridge Disconnected] React app closed the connection.{RESET}")


bridge.add_listener("connect", on_connect)
bridge.add_listener("disconnect", on_disconnect)


class AgentState(TypedDict):
    query: str
    goal: Goal
    registry: Dict[str, Any]
    values: Dict[str, Any]
    commands: List[Dict[str, Any]]
    action_history: List[Dict[str, Any]]
    consecutive_ineffective_count: int
    step_count: int
    status: str
    error: Optional[str]


def get_values_dict(bridge_instance) -> Dict[str, Any]:
    res = {}
    for comp in bridge_instance.graph.get_mounted_components():
        for slot_key, slot in comp.state_slots.items():
            res[f"{comp.id}.{slot_key}"] = slot.value
    return res


def plan_actions(state: AgentState) -> Dict[str, Any]:
    global PLANNER_MODEL, CONSECUTIVE_INEFFECTIVE_LIMIT
    
    registry_str = json.dumps(state["registry"], indent=2)
    values_str = json.dumps(state["values"], indent=2)
    
    history_lines = []
    for idx, item in enumerate(state["action_history"]):
        cmd = item["command"]
        changed = "produced state change" if item["state_changed"] else "ineffective (no state change)"
        history_lines.append(f"{idx+1}. Command: {json.dumps(cmd)} -> Result: {changed}")
    history_str = "\n".join(history_lines) if history_lines else "No actions executed yet."
    
    system_prompt = f"""You are an AI assistant controlling a React application state via a WebSocket Bridge.
You receive the component registry schema showing mounted components, their state slots, and interactive DOM elements:
---
REGISTRY SCHEMA:
{registry_str}
---
CURRENT STATE VALUES:
{values_str}
---
ACTION HISTORY (What you tried and what happened):
{history_str}
---

Your goal is to parse the user's natural language request and output a JSON array of commands to execute.

Available commands:
1. State assignment:
   {{"type": "setState", "commandId": "unique-id", "target": "ComponentID.stateKey", "value": val}}
2. Store actions:
   {{"type": "callAction", "commandId": "unique-id", "target": "ComponentID.actionName", "args": [arg1, arg2, ...]}}
3. DOM interactions (events):
   {{"type": "dispatchEvent", "commandId": "unique-id", "target": "ComponentID", "event": "click" | "focus" | "change", "payload": "selector-string-or-value"}}

CRITICAL RULES FOR COMMAND SELECTION:
- For any dispatchEvent command, the "target" field MUST ALWAYS be the Component ID (e.g. "SecurityPanel#r5"). The "payload" field MUST contain the CSS selector string of the element (e.g. "#tab-security" or "#btn-save-security"). NEVER put a CSS selector string in the "target" field.
- Always prefer dispatchEvent click commands for UI-based actions (such as clicking navigation tab buttons like '#tab-security', '#tab-controls', '#tab-status').
- Switching tabs changes the active component registry! Remember that components like 'SecurityPanel' or 'ControlsPanel' will only mount and show their state slots AFTER you click their corresponding tab button.
- Only use setState for inputs (like apiSecret, securityPin, newDevice).
- Respond ONLY with a valid JSON array of commands. No markdown blocks, no formatting.
"""

    if state["consecutive_ineffective_count"] >= CONSECUTIVE_INEFFECTIVE_LIMIT:
        system_prompt += f"\n\nWARNING: The last {state['consecutive_ineffective_count']} consecutive actions produced NO change in application state. You are stuck! Please reason about why the previous attempts were ineffective, avoid repeating the same command parameters, and try a fundamentally different approach."

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": state["query"]}
    ]
    
    try:
        print(f"Calling LLM ({PLANNER_MODEL}) to plan next actions...")
        response = litellm.completion(
            model=PLANNER_MODEL,
            messages=messages,
            temperature=0.0
        )
        content = response.choices[0].message.content.strip()
        
        import re
        match_json = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
        if match_json:
            content = match_json.group(1).strip()
        else:
            match_block = re.search(r"```\s*(.*?)\s*```", content, re.DOTALL)
            if match_block:
                content = match_block.group(1).strip()
            else:
                start = content.find("[")
                end = content.rfind("]")
                if start != -1 and end != -1 and end > start:
                    content = content[start:end+1].strip()
        
        commands = json.loads(content)
        if not isinstance(commands, list):
            commands = [commands]
        return {"commands": commands, "status": "planned"}
    except Exception as e:
        print(f"{RED}LLM planning failed: {e}{RESET}")
        return {"commands": [], "status": "failed", "error": f"LLM planning failed: {e}"}


async def execute_actions(state: AgentState) -> Dict[str, Any]:
    global bridge
    commands = state["commands"]
    if commands:
        await bridge.set_agent_status("working")
        
    action_history = list(state.get("action_history", []))
    consecutive_ineffective = state.get("consecutive_ineffective_count", 0)
    step_count = state.get("step_count", 0)
    
    for cmd in commands:
        if "error" in cmd:
            print(f"Plan contains error: {cmd['error']}")
            continue
            
        # 1. Repetition Check
        is_repetition = False
        for hist_item in action_history:
            hist_cmd = hist_item["command"]
            if (hist_cmd.get("type") == cmd.get("type") and
                hist_cmd.get("target") == cmd.get("target") and
                hist_cmd.get("value") == cmd.get("value") and
                hist_cmd.get("payload") == cmd.get("payload") and
                hist_cmd.get("args") == cmd.get("args") and
                not hist_item["state_changed"]):
                is_repetition = True
                break
                
        if is_repetition:
            print(f"{YELLOW}[Repetition Blocked] Command {cmd.get('type')} on {cmd.get('target')} was previously ineffective. Blocking execution and forcing replanning.{RESET}")
            action_history.append({
                "command": cmd,
                "state_changed": False,
                "blocked": True
            })
            consecutive_ineffective += 1
            step_count += 1
            return {
                "status": "replan",
                "action_history": action_history,
                "consecutive_ineffective_count": consecutive_ineffective,
                "step_count": step_count
            }

        # 2. Capture state before
        values_before = get_values_dict(bridge)

        # Dispatch command
        print(f"Executing command: {cmd.get('type')} -> {cmd.get('target')} (Value/Payload: {cmd.get('value') or cmd.get('payload')})")
        success = False
        try:
            bridge.graph.by_agent = True
            if cmd["type"] == "setState":
                success = await bridge.set_state(cmd["target"], cmd["value"])
            elif cmd["type"] == "dispatchEvent":
                success = await bridge.dispatch_event(cmd["target"], cmd["event"], cmd.get("payload"))
            elif cmd["type"] == "callAction":
                success = await bridge.call_action(cmd["target"], cmd["args"])
            elif cmd["type"] == "waitFor":
                cond = cmd["condition"]
                success = await bridge.wait_for(cmd["target"], cond["operator"], cond.get("value"), timeout_ms=cmd.get("timeoutMs", 5000))
        except Exception as e:
            print(f"{RED}Command execution failed: {e}{RESET}")
            success = False
        finally:
            bridge.graph.by_agent = False

        # 3. Capture state after and compare (polling up to 1.5s for async React state updates)
        state_changed = False
        for _ in range(30):
            await asyncio.sleep(0.05)
            values_after = get_values_dict(bridge)
            if values_before != values_after:
                state_changed = True
                break
        
        if state_changed:
            print(f"{GREEN}[Progress] Command produced observable state changes.{RESET}")
            consecutive_ineffective = 0
        else:
            print(f"{YELLOW}[Ineffective] Command produced NO state changes.{RESET}")
            consecutive_ineffective += 1

        # Record in action history
        action_history.append({
            "command": cmd,
            "state_changed": state_changed
        })
        
        step_count += 1

    return {
        "status": "executed",
        "action_history": action_history,
        "consecutive_ineffective_count": consecutive_ineffective,
        "step_count": step_count
    }


# Construct LangGraph Workflow
workflow = StateGraph(AgentState)
workflow.add_node("plan", plan_actions)
workflow.add_node("execute", execute_actions)

workflow.set_entry_point("plan")
workflow.add_edge("plan", "execute")


def should_continue(state: AgentState):
    if state["step_count"] >= state["goal"].max_steps:
        return END
        
    success_met = True
    for cond in state["goal"].success_conditions:
        if not cond.evaluate(bridge.graph):
            success_met = False
            break
            
    if state["goal"].success_conditions and success_met:
        return END
        
    if state["status"] == "failed":
        return END
        
    return "plan"


workflow.add_conditional_edges(
    "execute",
    should_continue,
    {
        "plan": "plan",
        END: END
    }
)

graph = workflow.compile()


async def cli_loop():
    print(f"\n=======================================================")
    print(f"{CYAN}AUI Smart Routing & Status Signal Agent{RESET}")
    print("Example Queries:")
    print("  1. Switch to Device Controls, add Smart Thermostat, adjust speed to 75")
    print("  2. Go to Security Settings, set PIN to 1234, save settings")
    print("  3. Navigate to Agent Status tab")
    print("  exit / quit - Shutdown agent")
    print(f"=======================================================\n")

    loop = asyncio.get_event_loop()
    while True:
        query = await loop.run_in_executor(None, lambda: input("Agent Query > ").strip())
        if not query:
            continue
        
        cmd_name = query.lower()

        if cmd_name in ["exit", "quit"]:
            print("Shutting down agent...")
            await bridge.stop()
            sys.exit(0)

        if not bridge.connection:
            print(f"{RED}Error: No React client connected. Please open the frontend in your browser.{RESET}")
            continue

        # Compile Goal
        snapshot = bridge.graph.snapshot()
        try:
            goal = await bridge.llm_adapter.compile_goal(query, snapshot)
            print(f"{GREEN}Successfully compiled Goal!{RESET}")
            print(f"  Description: {goal.description}")
            print(f"  Success Conditions:")
            for cond in goal.success_conditions:
                print(f"    - {cond.target} {cond.operator} {cond.value}")
        except Exception as e:
            print(f"{RED}Failed to compile goal: {e}{RESET}")
            continue

        # Build initial state
        state: AgentState = {
            "query": query,
            "goal": goal,
            "registry": snapshot.get("components", {}),
            "values": get_values_dict(bridge),
            "commands": [],
            "action_history": [],
            "consecutive_ineffective_count": 0,
            "step_count": 0,
            "status": "init",
            "error": None
        }

        # Run the workflow
        result = await graph.ainvoke(state, config={"recursion_limit": 100})

        # Check outcome
        success_met = True
        for cond in goal.success_conditions:
            if not cond.evaluate(bridge.graph):
                success_met = False
                break

        if goal.success_conditions and success_met:
            print(f"\n{GREEN}[Success] Goal accomplished! Steps taken: {result['step_count']}{RESET}")
            await bridge.set_agent_status("succeeded")
        elif result["step_count"] >= goal.max_steps:
            print(f"\n{RED}[Failure] Step budget exceeded without satisfying the goal!{RESET}")
            await bridge.set_agent_status("failed")
        else:
            print(f"\n{RED}[Failed] Planner loop finished without satisfying conditions.{RESET}")
            await bridge.set_agent_status("failed")


async def main():
    await bridge.start()
    print("Waiting for browser React application connection on port 8000...")
    await cli_loop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down server.")
