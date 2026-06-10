import asyncio
import json
import logging
import os
import re
import time
from typing import Dict, Any, List, Optional, TypedDict, Callable
import litellm
from langgraph.graph import StateGraph, END

from react_agent_bridge.core.client import ReactAgentBridge
from react_agent_bridge.core.planner.goal import Goal

logger = logging.getLogger("react_agent_bridge.runner")

# Terminal text colors
RED = "\033[1;31m"
YELLOW = "\033[1;33m"
GREEN = "\033[1;32m"
CYAN = "\033[1;36m"
RESET = "\033[0m"


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
    active_trace: Optional[Any]
    trace_step_index: Optional[int]
    initial_values: Optional[Dict[str, Any]]
    llm_calls_made: Optional[int]


class AgentRunner:
    """
    Standard agent execution wrapper. Compiles the LangGraph state machine,
    performs LLM planning, repetition checks, post-condition/progress tracking,
    and budget enforcement.
    """
    def __init__(
        self,
        bridge: ReactAgentBridge,
        model: str = "ollama/qwen2.5:7b",
        business_context: Optional[str] = None,
        max_steps: int = 20,
        planner_fn: Optional[Callable[[AgentState], Any]] = None,
        db_path: str = "discovery.db"
    ):
        self.bridge = bridge
        self.model = model
        self.business_context = business_context
        self.max_steps = max_steps
        self.planner_fn = planner_fn
        self.consecutive_ineffective_limit = 2
        self.db_path = db_path

        # Override/ensure the bridge uses our designated model for goal intake
        from react_agent_bridge.core.llm import LiteLLMAdapter
        if not getattr(self.bridge, "llm_adapter", None) or getattr(self.bridge.llm_adapter, "model", None) != model:
            self.bridge.llm_adapter = LiteLLMAdapter(model=model)

        # Suppress verbose LiteLLM and HTTPX logging
        logging.getLogger("litellm").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)

        # Construct and compile the LangGraph workflow
        workflow = StateGraph(AgentState)
        workflow.add_node("plan", self._plan_node)
        workflow.add_node("execute", self._execute_node)

        workflow.set_entry_point("plan")
        workflow.add_edge("plan", "execute")

        workflow.add_conditional_edges(
            "execute",
            self._should_continue,
            {
                "plan": "plan",
                END: END
            }
        )
        self.graph = workflow.compile()

    def _get_values_dict(self) -> Dict[str, Any]:
        res = {}
        for comp in self.bridge.graph.get_mounted_components():
            for slot_key, slot in comp.state_slots.items():
                res[f"{comp.id}.{slot_key}"] = slot.value
        return res

    def _plan_node(self, state: AgentState) -> Dict[str, Any]:
        # Initialize trace variables in state if missing
        active_trace = state.get("active_trace")
        idx = state.get("trace_step_index", 0)
        llm_calls_made = state.get("llm_calls_made", 0)

        # 1. Check if we have an active trace we are replaying
        if active_trace:
            steps = active_trace.steps
            if idx < len(steps):
                step = steps[idx]
                cmd = {"type": step.command_type, "target": step.target}
                if step.value is not None:
                    cmd["value"] = step.value
                if step.event is not None:
                    cmd["event"] = step.event
                if step.selector is not None:
                    cmd["payload"] = step.selector
                if step.args is not None:
                    cmd["args"] = step.args
                
                print(f"{CYAN}[Trace Replay] Replaying step {idx+1}/{len(steps)}: {json.dumps(cmd)}{RESET}")
                return {
                    "commands": [cmd],
                    "status": "planned",
                    "trace_step_index": idx
                }
            else:
                print(f"{YELLOW}[Trace Replay] Completed trace, but goal conditions not met. Falling back to LLM.{RESET}")
                state["active_trace"] = None
                active_trace = None

        # 2. If no active trace, query the store for applicable traces
        if not active_trace:
            try:
                from react_agent_bridge.discovery.traces import GoldenTraceStore
                store = GoldenTraceStore(self.db_path)
                traces = store.find_applicable_traces(state["goal"].description, state["values"], min_confidence=0.8)
                if traces:
                    trace = traces[0]
                    state["active_trace"] = trace
                    state["trace_step_index"] = 0
                    print(f"{CYAN}[Trace Replay] Found applicable golden trace (ID: {trace.trace_id}) with confidence {trace.confidence:.2f}. Replaying...{RESET}")
                    
                    step = trace.steps[0]
                    cmd = {"type": step.command_type, "target": step.target}
                    if step.value is not None:
                        cmd["value"] = step.value
                    if step.event is not None:
                        cmd["event"] = step.event
                    if step.selector is not None:
                        cmd["payload"] = step.selector
                    if step.args is not None:
                        cmd["args"] = step.args
                        
                    return {
                        "commands": [cmd],
                        "status": "planned",
                        "active_trace": trace,
                        "trace_step_index": 0
                    }
            except Exception as e:
                logger.error(f"Failed to query trace store: {e}")

        # Increment LLM calls
        llm_calls_made += 1

        # If a custom planner callback is registered, attempt to run it first
        if self.planner_fn:
            try:
                res = self.planner_fn(state)
                if res is not None:
                    if isinstance(res, list):
                        return {"commands": res, "status": "planned", "llm_calls_made": llm_calls_made}
                    elif isinstance(res, dict):
                        # Ensure llm_calls_made is included
                        res["llm_calls_made"] = llm_calls_made
                        return res
            except Exception as e:
                logger.error(f"Custom planner_fn failed: {e}")

        # Default LiteLLM planning logic
        registry_str = json.dumps(state["registry"], indent=2)
        values_str = json.dumps(state["values"], indent=2)

        history_lines = []
        for h_idx, item in enumerate(state["action_history"]):
            cmd = item["command"]
            changed = "produced state change" if item["state_changed"] else "ineffective (no state change)"
            history_lines.append(f"{h_idx+1}. Command: {json.dumps(cmd)} -> Result: {changed}")
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
- Always prefer dispatchEvent click commands for UI-based actions (such as clicking navigation tab buttons or other buttons).
- Only use setState for inputs.
- Respond ONLY with a valid JSON array of commands. No markdown blocks, no formatting.
"""
        if self.business_context:
            system_prompt += f"\n\nBUSINESS CONTEXT & CRITICAL RULES:\n{self.business_context}"

        if state["consecutive_ineffective_count"] >= self.consecutive_ineffective_limit:
            system_prompt += f"\n\nWARNING: The last {state['consecutive_ineffective_count']} consecutive actions produced NO change in application state. You are stuck! Please reason about why the previous attempts were ineffective, avoid repeating the same command parameters, and try a fundamentally different approach."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": state["query"]}
        ]

        try:
            print(f"Calling LLM ({self.model}) to plan next actions...")
            response = litellm.completion(
                model=self.model,
                messages=messages,
                temperature=0.0
            )
            content = response.choices[0].message.content.strip()

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
            return {"commands": commands, "status": "planned", "llm_calls_made": llm_calls_made}
        except Exception as e:
            print(f"{RED}LLM planning failed: {e}{RESET}")
            return {"commands": [], "status": "failed", "error": f"LLM planning failed: {e}", "llm_calls_made": llm_calls_made}

    async def _execute_node(self, state: AgentState) -> Dict[str, Any]:
        commands = state["commands"]
        if commands:
            await self.bridge.set_agent_status("working")

        action_history = list(state.get("action_history", []))
        consecutive_ineffective = state.get("consecutive_ineffective_count", 0)
        step_count = state.get("step_count", 0)
        active_trace = state.get("active_trace")
        trace_step_index = state.get("trace_step_index", 0)

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
            values_before = self._get_values_dict()

            # Dispatch command
            print(f"Executing command: {cmd.get('type')} -> {cmd.get('target')} (Value/Payload: {cmd.get('value') or cmd.get('payload')})")
            success = False
            start_time = time.time()
            try:
                self.bridge.graph.by_agent = True
                if cmd["type"] == "setState":
                    success = await self.bridge.set_state(cmd["target"], cmd["value"])
                elif cmd["type"] == "dispatchEvent":
                    success = await self.bridge.dispatch_event(cmd["target"], cmd["event"], cmd.get("payload"))
                elif cmd["type"] == "callAction":
                    success = await self.bridge.call_action(cmd["target"], cmd["args"])
                elif cmd["type"] == "waitFor":
                    cond = cmd["condition"]
                    success = await self.bridge.wait_for(cmd["target"], cond["operator"], cond.get("value"), timeout_ms=cmd.get("timeoutMs", 5000))
            except Exception as e:
                print(f"{RED}Command execution failed: {e}{RESET}")
                success = False
            finally:
                self.bridge.graph.by_agent = False

            # 3. Capture state after and compare (polling up to 1.5s for async React state updates)
            state_changed = False
            settle_time_ms = 0.0
            for _ in range(30):
                await asyncio.sleep(0.05)
                values_after = self._get_values_dict()
                if values_before != values_after:
                    state_changed = True
                    break

            settle_time_ms = (time.time() - start_time) * 1000.0

            if state_changed:
                print(f"{GREEN}[Progress] Command produced observable state changes.{RESET}")
                consecutive_ineffective = 0
            else:
                print(f"{YELLOW}[Ineffective] Command produced NO state changes.{RESET}")
                consecutive_ineffective += 1

            # Record in action history with detailed metrics
            action_history.append({
                "command": cmd,
                "state_changed": state_changed,
                "pre_state": values_before,
                "post_state": values_after,
                "settle_time_ms": settle_time_ms
            })

            step_count += 1

            # 4. If replaying active trace, check post-condition
            if active_trace:
                steps = active_trace.steps
                if trace_step_index < len(steps):
                    step = steps[trace_step_index]
                    # Compare actual post_state values_after with step's expected post_state_snapshot
                    mismatch = False
                    for k, val in step.post_state_snapshot.items():
                        if values_after.get(k) != val:
                            mismatch = True
                            break
                    
                    if not mismatch:
                        trace_step_index += 1
                        print(f"{GREEN}[Trace Replay] Step {trace_step_index}/{len(steps)} verified successfully.{RESET}")
                    else:
                        print(f"{RED}[Trace Replay] Post-state mismatch at step {trace_step_index+1}. Decaying confidence and falling back to LLM.{RESET}")
                        try:
                            from react_agent_bridge.discovery.traces import GoldenTraceStore
                            store = GoldenTraceStore(self.db_path)
                            store.update_trace_confidence(active_trace.trace_id, succeeded=False)
                        except Exception as e:
                            logger.error(f"Failed to decay trace: {e}")
                        active_trace = None
                        trace_step_index = 0

        return {
            "status": "executed",
            "action_history": action_history,
            "consecutive_ineffective_count": consecutive_ineffective,
            "step_count": step_count,
            "active_trace": active_trace,
            "trace_step_index": trace_step_index
        }

    def _should_continue(self, state: AgentState):
        if state["step_count"] >= state["goal"].max_steps:
            return END

        success_met = True
        for cond in state["goal"].success_conditions:
            if not cond.evaluate(self.bridge.graph):
                success_met = False
                break

        if state["goal"].success_conditions and success_met:
            return END

        if state["status"] == "failed":
            return END

        return "plan"

    async def execute(self, query: str) -> dict:
        """
        Executes a natural language query against the bridge.
        """
        if not self.bridge.connection:
            print(f"{RED}Error: No React client connected. Please open the frontend in your browser.{RESET}")
            return {"status": "failed", "error": "No connection"}

        # 1. Compile Goal
        snapshot = self.bridge.graph.snapshot()
        try:
            goal = await self.bridge.llm_adapter.compile_goal(query, snapshot)
            print(f"{GREEN}Successfully compiled Goal!{RESET}")
            print(f"  Description: {goal.description}")
            print(f"  Success Conditions:")
            for cond in goal.success_conditions:
                print(f"    - {cond.target} {cond.operator} {cond.value}")
            if goal.failure_conditions:
                print(f"  Failure Conditions:")
                for cond in goal.failure_conditions:
                    print(f"    - {cond.target} {cond.operator} {cond.value}")
        except Exception as e:
            print(f"{RED}Failed to compile goal: {e}{RESET}")
            return {"status": "failed", "error": str(e)}

        # Ensure goal step limit respects runner limit
        goal.max_steps = self.max_steps

        # 2. Build initial state
        initial_val = self._get_values_dict()
        state: AgentState = {
            "query": query,
            "goal": goal,
            "registry": snapshot.get("components", {}),
            "values": initial_val,
            "commands": [],
            "action_history": [],
            "consecutive_ineffective_count": 0,
            "step_count": 0,
            "status": "init",
            "error": None,
            "active_trace": None,
            "trace_step_index": 0,
            "initial_values": initial_val,
            "llm_calls_made": 0
        }

        # 3. Run the workflow
        start_exec_time = time.time()
        result = await self.graph.ainvoke(state, config={"recursion_limit": 100})

        # 4. Check outcome and update status
        success_met = True
        for cond in goal.success_conditions:
            if not cond.evaluate(self.bridge.graph):
                success_met = False
                break

        if goal.success_conditions and success_met:
            print(f"\n{GREEN}[Success] Goal accomplished! Steps taken: {result['step_count']}{RESET}")
            await self.bridge.set_agent_status("succeeded")

            # Handle Golden Trace recording / update
            try:
                active_trace = result.get("active_trace")
                from react_agent_bridge.discovery.traces import GoldenTraceStore
                store = GoldenTraceStore(self.db_path)
                
                if active_trace:
                    # Successfully replayed trace: promote its confidence
                    print(f"{GREEN}[Trace Replay] Replayed trace successfully. Promoting confidence...{RESET}")
                    store.update_trace_confidence(active_trace.trace_id, succeeded=True)
                else:
                    # Planned via LLM: record new trace if we actually had valid steps
                    valid_steps = [h for h in result.get("action_history", []) if not h.get("blocked")]
                    if valid_steps:
                        import uuid
                        from react_agent_bridge.discovery.traces import GoldenTrace, GoldenTraceStep
                        
                        steps = []
                        for h in valid_steps:
                            cmd = h["command"]
                            steps.append(GoldenTraceStep(
                                command_type=cmd["type"],
                                target=cmd["target"],
                                value=cmd.get("value"),
                                event=cmd.get("event"),
                                selector=cmd.get("payload"),
                                args=cmd.get("args"),
                                pre_state_snapshot=h.get("pre_state", {}),
                                post_state_snapshot=h.get("post_state", {}),
                                settle_time_ms=h.get("settle_time_ms", 0.0)
                            ))

                        import hashlib
                        mounted = self.bridge.graph.get_mounted_components()
                        names = sorted([c.display_name for c in mounted])
                        app_version_hash = hashlib.md5(json.dumps(names).encode("utf-8")).hexdigest()[:16]

                        trace = GoldenTrace(
                            trace_id=str(uuid.uuid4()),
                            workflow_name=goal.description,
                            goal_description=query,
                            recorded_at=time.time(),
                            application_version_hash=app_version_hash,
                            precondition_state=result.get("initial_values", {}),
                            steps=steps,
                            postcondition_state=self._get_values_dict(),
                            execution_time_ms=(time.time() - start_exec_time) * 1000.0,
                            llm_calls_made=result.get("llm_calls_made", 0),
                            confidence=1.0
                        )
                        store.record_trace(trace)
                        print(f"{GREEN}[Trace Replay] Successfully recorded new golden trace (ID: {trace.trace_id}){RESET}")
            except Exception as e:
                logger.error(f"Failed to record/update trace: {e}", exc_info=True)

        elif result["step_count"] >= goal.max_steps:
            print(f"\n{RED}[Failure] Step budget exceeded without satisfying the goal!{RESET}")
            if "action_history" in result:
                print("Sequence of failed actions:")
                for idx, item in enumerate(result["action_history"]):
                    print(f"  {idx+1}. Command: {json.dumps(item['command'])} | State Changed: {item['state_changed']}")
            print("\nLast known state values:")
            for target, val in self._get_values_dict().items():
                print(f"  {target} = {val}")
            await self.bridge.set_agent_status("failed")
        else:
            print(f"\n{RED}[Failed] Planner loop finished without satisfying conditions. Error: {result.get('error')}{RESET}")
            await self.bridge.set_agent_status("failed")

        return result
