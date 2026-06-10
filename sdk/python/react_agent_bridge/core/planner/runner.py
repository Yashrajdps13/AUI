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
MAGENTA = "\033[1;35m"
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

    def _compute_goal_signature(self, goal: Goal) -> str:
        sig_parts = []
        for cond in goal.success_conditions:
            parts = cond.target.rsplit(".", 1)
            if len(parts) == 2:
                comp_id, slot_key = parts
                clean_comp = comp_id.split("#", 1)[0]
                sig_parts.append(f"{clean_comp}.{slot_key}:{cond.operator}")
        sig_parts.sort()
        return ",".join(sig_parts)

    async def _decompose_goal(self, query: str) -> List[str]:
        if self.model == "mock-model":
            return [query]
        try:
            import litellm
            messages = [
                {"role": "system", "content": "You are a task decomposer that breaks down user requests into a JSON list of sequential strings representing execution stages. Output strictly valid JSON only."},
                {"role": "user", "content": f"""Decompose the following goal into a JSON list of sequential, single-step execution stages:
Goal: "{query}"

Output strictly a JSON array of strings, e.g. ["stage 1", "stage 2"]. Do not add any markdown formatting or extra text."""}
            ]
            response = litellm.completion(
                model=self.model,
                messages=messages,
                temperature=0.0
            )
            content = response.choices[0].message.content.strip()
            # Clean markdown code blocks if present
            content = content.replace("```json", "").replace("```", "").strip()
            stages = json.loads(content)
            if isinstance(stages, list) and all(isinstance(s, str) for s in stages):
                return stages
        except Exception as e:
            logger.warning(f"Decomposition failed, using original goal as a single stage: {e}")
        return [query]

    def _plan_node(self, state: AgentState) -> Dict[str, Any]:
        # Initialize trace variables in state if missing
        active_trace = state.get("active_trace")
        idx = state.get("trace_step_index", 0)
        llm_calls_made = state.get("llm_calls_made", 0)

        # Helper to compute structural signature of goal
        def compute_goal_signature(goal: Goal) -> str:
            return self._compute_goal_signature(goal)


        # Helper to parameterize golden trace commands based on current goal
        def get_parameterized_cmd(step: Any, trace: Any, current_goal: Goal) -> Optional[dict]:
            # Create a mapping from clean component name to active component ID
            # Use the LIVE graph (not stale initial snapshot) so navigation between pages works
            clean_to_active_id = {}
            for active_id in self.bridge.graph.components.keys():
                clean_name = active_id.split("#", 1)[0]
                clean_to_active_id[clean_name] = active_id

            # Helper to map a recorded target to the active target
            def map_target(recorded_target: str) -> str:
                if not recorded_target:
                    return recorded_target
                if "." in recorded_target:
                    comp_part, slot_part = recorded_target.rsplit(".", 1)
                    comp_clean = comp_part.split("#", 1)[0]
                    active_comp = clean_to_active_id.get(comp_clean, comp_part)
                    return f"{active_comp}.{slot_part}"
                else:
                    comp_clean = recorded_target.split("#", 1)[0]
                    return clean_to_active_id.get(comp_clean, recorded_target)

            active_target = map_target(step.target)
            cmd = {"type": step.command_type, "target": active_target}
            if step.event is not None:
                cmd["event"] = step.event
            if step.args is not None:
                cmd["args"] = step.args
                
            val_map = {}
            for cond in current_goal.success_conditions:
                if cond.operator not in ["equals", "includes"]:
                    continue
                parts = cond.target.rsplit(".", 1)
                if len(parts) != 2:
                    continue
                curr_comp, curr_slot = parts
                curr_comp_clean = curr_comp.split("#", 1)[0]
                
                for trace_target, trace_val in trace.postcondition_state.items():
                    t_parts = trace_target.rsplit(".", 1)
                    if len(t_parts) == 2:
                        t_comp, t_slot = t_parts
                        t_comp_clean = t_comp.split("#", 1)[0]
                        if t_comp_clean == curr_comp_clean and t_slot == curr_slot:
                            val_map[trace_target] = (trace_val, cond.value)
                            break

            if step.command_type == "setState":
                val = step.value
                target_comp, target_slot = step.target.rsplit(".", 1) if "." in step.target else (step.target, "")
                target_comp_clean = target_comp.split("#", 1)[0]
                
                for orig_target, (orig_val, curr_val) in val_map.items():
                    orig_comp, orig_slot = orig_target.rsplit(".", 1)
                    orig_comp_clean = orig_comp.split("#", 1)[0]
                    if orig_comp_clean == target_comp_clean and orig_slot == target_slot:
                        val = curr_val
                        break
                cmd["value"] = val
                
            elif step.command_type == "dispatchEvent" and step.selector:
                selector = step.selector
                
                for orig_target, (orig_val, curr_val) in val_map.items():
                    if isinstance(orig_val, list) and isinstance(curr_val, list):
                        matched_item_idx = -1
                        for i, item in enumerate(orig_val):
                            slug = re.sub(r'[^a-z0-9]+', '-', str(item).lower()).strip('-')
                            if slug and slug in selector:
                                matched_item_idx = i
                                break
                        
                        if matched_item_idx != -1:
                            if matched_item_idx < len(curr_val):
                                new_item = curr_val[matched_item_idx]
                                slug_orig = re.sub(r'[^a-z0-9]+', '-', str(orig_val[matched_item_idx]).lower()).strip('-')
                                slug_curr = re.sub(r'[^a-z0-9]+', '-', str(new_item).lower()).strip('-')
                                selector = selector.replace(slug_orig, slug_curr)
                                selector = selector.replace(str(orig_val[matched_item_idx]), str(new_item))
                            else:
                                return None
                    else:
                        slug_orig = re.sub(r'[^a-z0-9]+', '-', str(orig_val).lower()).strip('-')
                        slug_curr = re.sub(r'[^a-z0-9]+', '-', str(curr_val).lower()).strip('-')
                        if slug_orig and slug_orig in selector:
                            selector = selector.replace(slug_orig, slug_curr)
                        if str(orig_val) in selector:
                            selector = selector.replace(str(orig_val), str(curr_val))
                            
                cmd["payload"] = selector
            else:
                if step.value is not None:
                    cmd["value"] = step.value
                if step.selector is not None:
                    cmd["payload"] = step.selector
                    
            return cmd

        # 1. Check if we have an active trace we are replaying
        if active_trace:
            steps = active_trace.steps
            while idx < len(steps):
                step = steps[idx]
                cmd = get_parameterized_cmd(step, active_trace, state["goal"])
                if cmd is None:
                    # Skip step because the new collection list has fewer items
                    idx += 1
                    state["trace_step_index"] = idx
                    continue

                print(f"{CYAN}[Trace Replay] Replaying step {idx+1}/{len(steps)}: {json.dumps(cmd)}{RESET}")
                return {
                    "commands": [cmd],
                    "status": "planned",
                    "trace_step_index": idx
                }

            # Reached past end of steps
            print(f"{YELLOW}[Trace Replay] Completed trace, but goal conditions not met. Falling back to LLM.{RESET}")
            state["active_trace"] = None
            active_trace = None

        # 2. If no active trace, query the store for applicable traces
        if not active_trace:
            try:
                from react_agent_bridge.discovery.traces import GoldenTraceStore
                store = GoldenTraceStore(self.db_path)
                sig = compute_goal_signature(state["goal"])
                traces = store.find_applicable_traces(state["goal"].description, state["values"], min_confidence=0.8, structural_signature=sig)
                if traces:
                    trace = traces[0]
                    state["active_trace"] = trace
                    state["trace_step_index"] = 0
                    print(f"{CYAN}[Trace Replay] Found applicable golden trace (ID: {trace.trace_id}) with confidence {trace.confidence:.2f}. Replaying...{RESET}")
                    
                    while state["trace_step_index"] < len(trace.steps):
                        step = trace.steps[state["trace_step_index"]]
                        cmd = get_parameterized_cmd(step, trace, state["goal"])
                        if cmd is None:
                            state["trace_step_index"] += 1
                            continue
                        
                        return {
                            "commands": [cmd],
                            "status": "planned",
                            "active_trace": trace,
                            "trace_step_index": state["trace_step_index"]
                        }
            except Exception as e:
                logger.error(f"Failed to query trace store: {e}", exc_info=True)

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
        # IMPORTANT: Always refresh registry and values from the LIVE graph so we see the
        # current page's components/elements (not the stale initial snapshot).
        live_snapshot = self.bridge.graph.snapshot()
        live_values = self._get_values_dict()
        state["registry"] = live_snapshot
        state["values"] = live_values


        # Build a concise, flat representation of the current registry for the LLM.
        # This prevents small models from getting confused by deeply-nested JSON.
        components_info = live_snapshot.get("components", {})
        registry_lines = []
        allowed_set_targets = []  # "ComponentID.slotKey" strings for setState
        allowed_call_targets = []  # "ComponentID.actionName" strings for callAction
        allowed_selectors_by_comp = {}  # ComponentID -> [selector, ...]

        for comp_id, comp in components_info.items():
            registry_lines.append(f"Component: {comp_id} (displayName={comp.get('displayName','?')}, route={comp.get('route','?')})")
            slots = comp.get("stateSlots", {})
            descs = comp.get("stateSlotDescriptions", {})
            for slot_key, slot_val in slots.items():
                desc = descs.get(slot_key, "")
                registry_lines.append(f"  stateSlot: {slot_key} = {json.dumps(slot_val)}" + (f"  # {desc}" if desc else ""))
                # Prohibit direct setState on collections (lists or dicts with multiple keys)
                is_collection = isinstance(slot_val, list) or (isinstance(slot_val, dict) and len(slot_val) > 1)
                if not is_collection:
                    allowed_set_targets.append(f"{comp_id}.{slot_key}")
            elems = comp.get("interactiveElements", [])
            comp_selectors = []
            for el in elems:
                sel = el.get('selector', '')
                tag = el.get('tagName', '')
                text = el.get('text', '') or ''
                disabled = el.get('disabled', False)
                visible = el.get('visible', True)
                if sel and visible and not disabled:
                    registry_lines.append(f"  interactiveElement: selector={sel!r}  tag={tag}  text={text!r}")
                    comp_selectors.append(sel)
                elif sel:
                    registry_lines.append(f"  interactiveElement: selector={sel!r}  tag={tag}  text={text!r}  [DISABLED or HIDDEN]")
            if comp_selectors:
                allowed_selectors_by_comp[comp_id] = comp_selectors
            actions = comp.get("actions", [])
            for action in (actions or []):
                registry_lines.append(f"  action: {action}")
                allowed_call_targets.append(f"{comp_id}.{action}")

        registry_str = "\n".join(registry_lines) if registry_lines else "(empty - no components mounted yet)"
        values_str = json.dumps(live_values, indent=2)

        # Build explicit allowed-selector reference for the LLM
        selector_lines = []
        for comp_id, sels in allowed_selectors_by_comp.items():
            selector_lines.append(f"  {comp_id}: " + ", ".join(sels))
        allowed_selectors_str = "\n".join(selector_lines) if selector_lines else "  (none visible)"

        # Build allowed callAction targets list (only real registered actions)
        allowed_call_str = ("\n".join("  " + t for t in allowed_call_targets)
                            if allowed_call_targets else "  (none — do NOT use callAction)")

        # Detect current UI step and provide specific navigation guidance
        step_hint_lines = []
        step_nav_map = {
            "details":  "Fill attendeeName and email, then click the 'Next Step' button (#btn-details-next).",
            "options":  "Click the session toggle buttons to select sessions, then click the 'Next Step' button (#btn-options-next).",
            "payment":  "Fill cardNumber, then click the 'Confirm and Pay' button (#btn-submit-booking) to submit.",
        }
        for comp_id in components_info:
            active_step = live_values.get(f"{comp_id}.activeStep")
            if active_step and active_step in step_nav_map:
                step_hint_lines.append(
                    f"CURRENT STEP: '{active_step}'. Instruction: {step_nav_map[active_step]}"
                )
                break
        step_hint_str = "\n".join(step_hint_lines) if step_hint_lines else ""

        history_lines = []
        for h_idx, item in enumerate(state["action_history"]):
            cmd = item["command"]
            if item.get("rejected"):
                changed = f"REJECTED - {item.get('error')}"
            elif item.get("skipped"):
                changed = "SKIPPED (already has value)"
            else:
                changed = "produced state change" if item["state_changed"] else "ineffective (no state change)"
            history_lines.append(f"{h_idx+1}. Command: {json.dumps(cmd)} -> Result: {changed}")
        history_str = "\n".join(history_lines) if history_lines else "No actions executed yet."

        # Compute which goal success conditions are already satisfied by the current live state.
        # Show these to the LLM so it knows NOT to re-click toggle buttons that are already done.
        goal = state.get("goal")
        satisfied_lines = []
        unsatisfied_lines = []
        if goal and hasattr(goal, "success_conditions"):
            for cond in goal.success_conditions:
                cond_target = cond.target  # e.g. "App#r9.selectedSessions"
                cond_op = cond.operator    # e.g. "includes", "equals", "truthy"
                cond_val = cond.value
                raw_values = self._get_values_dict()
                current_live = None
                cond_target_comp, cond_target_slot = cond_target.rsplit(".", 1) if "." in cond_target else (cond_target, "")
                cond_target_comp_clean = cond_target_comp.split("#", 1)[0].split(":", 1)[0]
                
                for k, v in raw_values.items():
                    k_comp, k_slot = k.rsplit(".", 1) if "." in k else (k, "")
                    k_comp_clean = k_comp.split("#", 1)[0].split(":", 1)[0]
                    if k_comp_clean == cond_target_comp_clean and k_slot == cond_target_slot:
                        current_live = v
                        break
                
                is_sat = False
                if cond_op == "equals":
                    is_sat = current_live == cond_val
                elif cond_op == "includes":
                    is_sat = isinstance(current_live, list) and cond_val in current_live
                elif cond_op == "truthy":
                    is_sat = bool(current_live)
                elif cond_op == "falsy":
                    is_sat = not bool(current_live)
                label = f"{cond_target} {cond_op} {cond_val}"
                if is_sat:
                    satisfied_lines.append(f"  ✓ {label}")
                else:
                    unsatisfied_lines.append(f"  ✗ {label}")

        satisfied_str = "\n".join(satisfied_lines) if satisfied_lines else "  (none yet)"
        unsatisfied_str = "\n".join(unsatisfied_lines) if unsatisfied_lines else "  (all done!)"

        system_prompt = f"""You are an AI assistant controlling a React application via a WebSocket Bridge.
Below is the CURRENT state of mounted components and their interactive elements.

---
COMPONENT REGISTRY (current page only):
{registry_str}
---
CURRENT STATE VALUES:
{values_str}
---
ACTION HISTORY (What you tried and what happened):
{history_str}
---
GOAL CONDITIONS — ALREADY SATISFIED (do NOT perform any actions to change these):
{satisfied_str}
---
GOAL CONDITIONS — STILL NEEDED:
{unsatisfied_str}
---
{(step_hint_str + chr(10) + '---' + chr(10)) if step_hint_str else ''}
Your goal is to fulfill the user request by outputting a JSON array of bridge commands.
Only work on the STILL NEEDED conditions above. DO NOT re-do any ALREADY SATISFIED condition.

Available command types:
1. setState      -> {{"type":"setState",      "target":"<ComponentID.slotKey>", "value":<val>}}
2. callAction    -> {{"type":"callAction",    "target":"<ComponentID.actionName>", "args":[...]}}
3. dispatchEvent -> {{"type":"dispatchEvent", "target":"<ComponentID>", "event":"click"|"change"|"focus", "payload":"<css-selector>"}}
4. waitFor       -> {{"type":"waitFor",       "target":"<ComponentID>|<ComponentID.slotKey>", "condition": {{"operator":"truthy"|"falsy"|"equals", "value":<val>}}, "timeoutMs":5000}}

ALLOWED setState targets (ONLY use these exact strings for the target field of setState commands):
{chr(10).join('  ' + t for t in allowed_set_targets)}

ALLOWED callAction targets (ONLY use these exact strings; if list is empty, do NOT use callAction):
{allowed_call_str}

ALLOWED dispatchEvent selectors per component (ONLY use these exact selector strings as payload):
{allowed_selectors_str}

CRITICAL RULES - follow these exactly:
1. Every target in every command (setState target, callAction target, dispatchEvent target and payload selector) MUST exactly match something currently visible in the COMPONENT REGISTRY or the ALLOWED lists above.
2. DO NOT invent, guess, or reference any component IDs, slot names, action names, or selectors based on what you think should exist (e.g. from the goal description). If they are not in the registry snapshot, they do not exist.
3. If a component, slot, action, or selector that you need is not in the registry snapshot yet, DO NOT guess it. Instead, you MUST use the `waitFor` command to wait for the target to appear, or stop.
4. For dispatchEvent: "target" = ComponentID (e.g. "App#r9"), "payload" = css selector (e.g. "#btn-details-next"). NEVER swap these.
5. Plan commands for the CURRENT page/step only. After clicking a page navigation button (Next/Submit/Pay), stop — the planner re-runs for the next page.
6. If a slot already has the correct value, skip its setState command.
7. NEVER call setState on array/list slots (e.g. selectedSessions). Click the corresponding toggle button instead.
8. Toggle buttons (e.g. session checkboxes) are ON/OFF — clicking again will REMOVE the item. If the condition is already satisfied, do NOT click that button again.
9. Respond ONLY with a valid JSON array. No markdown fences, no extra text.
10. Do NOT perform setState on state slots whose corresponding input/interactive elements are not currently visible in the COMPONENT REGISTRY. For example, if a form field input (such as cardNumber or selectedSessions) is not rendered on the current screen, do not set its state slot value until you navigate to the screen where it is rendered.
11. If the required component is not mounted yet, wait for it to appear. Never plan actions on unmounted components."""
        if self.business_context:
            system_prompt += f"\n\nBUSINESS CONTEXT & CRITICAL RULES:\n{self.business_context}"

        # Stuck-detection for consecutive target rejections
        target_rejections = {}
        for hist_item in reversed(state["action_history"]):
            hist_cmd = hist_item["command"]
            h_target = hist_cmd.get("target")
            if not h_target:
                continue
            if h_target not in target_rejections:
                target_rejections[h_target] = {"count": 0, "active": True}
            
            if target_rejections[h_target]["active"]:
                if hist_item.get("rejected"):
                    target_rejections[h_target]["count"] += 1
                else:
                    target_rejections[h_target]["active"] = False
                    
        reframe_warnings = []
        for h_target, info in target_rejections.items():
            if info["count"] >= 3:
                reframe_warnings.append(
                    f"WARNING: The command target '{h_target}' was rejected {info['count']} times in a row because it was not found in the current component registry. "
                    "This component or state slot is not currently mounted (it may have been unmounted due to a successful action, such as logging in or navigating). "
                    "You MUST read the COMPONENT REGISTRY and CURRENT STATE VALUES above, identify which components are actually mounted right now, and plan your actions using only the currently mounted elements."
                )
        if reframe_warnings:
            system_prompt += "\n\n" + "\n".join(reframe_warnings)

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

            # Truncate batch at the first navigation click (page change) but keep it
            truncated = []
            for raw_cmd in commands:
                cmd_type = raw_cmd.get("type")
                truncated.append(raw_cmd)
                if cmd_type == "dispatchEvent" and raw_cmd.get("event") == "click":
                    nav_indicators = ["btn-next", "btn-pay", "btn-submit", "btn-reset", "btn-back", "-next", "-pay"]
                    payload = raw_cmd.get("payload", "") or ""
                    if any(ind in payload.lower() for ind in nav_indicators):
                        print(f"{CYAN}[Sanitizer] Navigation click detected ({payload!r}), truncating batch to prevent multi-page planning.{RESET}")
                        break
            commands = truncated

            return {
                "commands": commands,
                "status": "planned",
                "llm_calls_made": llm_calls_made,
                "registry": live_snapshot,
                "values": live_values
            }
        except Exception as e:
            print(f"{RED}LLM planning failed: {e}{RESET}")
            return {
                "commands": [],
                "status": "failed",
                "error": f"LLM planning failed: {e}",
                "llm_calls_made": llm_calls_made,
                "registry": live_snapshot,
                "values": live_values
            }

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

            # --- Live validation & Sanitization ---
            live_snapshot = self.bridge.graph.snapshot()
            live_values = self._get_values_dict()
            components_info = live_snapshot.get("components", {})
            
            allowed_set_targets = []
            allowed_call_targets = []
            all_allowed_selectors_set = set()
            
            for comp_id, comp in components_info.items():
                slots = comp.get("stateSlots", {})
                for slot_key, slot_val in slots.items():
                    is_collection = isinstance(slot_val, list) or (isinstance(slot_val, dict) and len(slot_val) > 1)
                    if not is_collection:
                        allowed_set_targets.append(f"{comp_id}.{slot_key}")
                
                elems = comp.get("interactiveElements", [])
                for el in elems:
                    sel = el.get("selector", "")
                    visible = el.get("visible", True)
                    disabled = el.get("disabled", False)
                    if sel and visible and not disabled:
                        all_allowed_selectors_set.add(sel)
                
                actions = comp.get("actions", [])
                for action in (actions or []):
                    allowed_call_targets.append(f"{comp_id}.{action}")
                    
            allowed_set_targets_set = set(allowed_set_targets)
            allowed_call_targets_set = set(allowed_call_targets)
            
            cmd_type = cmd.get("type")
            rejection_reason = None
            is_skipped = False
            
            if cmd_type == "setState":
                target = cmd.get("target", "")
                if target not in allowed_set_targets_set:
                    rejection_reason = f"Command rejected: target '{target}' is not in the current registry. The component may have unmounted. Check the current registry before retrying."
                else:
                    desired_val = cmd.get("value")
                    current_val = live_values.get(target)
                    if current_val == desired_val:
                        is_skipped = True
            elif cmd_type == "callAction":
                target = cmd.get("target", "")
                if "." not in target:
                    rejection_reason = f"Command rejected: malformed callAction target '{target}' (missing action name)."
                elif target not in allowed_call_targets_set:
                    rejection_reason = f"Command rejected: target action '{target}' is not registered. Check the current registry before retrying."
            elif cmd_type == "dispatchEvent":
                payload = cmd.get("payload")
                if isinstance(payload, str) and (payload.startswith("#") or payload.startswith(".")):
                    if payload not in all_allowed_selectors_set:
                        rejection_reason = f"Command rejected: selector '{payload}' is not in the current registry. The component may have unmounted or selector is invalid. Check the current registry before retrying."
            elif cmd_type == "waitFor":
                target = cmd.get("target", "")
                if any(x in target.lower() for x in ["consolelogs", "applog", "logs"]):
                    rejection_reason = f"Command rejected: waitFor target '{target}' contains a debug ledger or log field. WaitFor is for application state slots only."
            
            if rejection_reason:
                print(f"{YELLOW}[Sanitizer] Rejected command: {rejection_reason}{RESET}")
                action_history.append({
                    "command": cmd,
                    "state_changed": False,
                    "error": rejection_reason,
                    "rejected": True
                })
                consecutive_ineffective += 1
                step_count += 1
                continue
                
            if is_skipped:
                target = cmd.get("target", "")
                print(f"{CYAN}[Sanitizer] Skipping setState on {target!r} — already has value {json.dumps(cmd.get('value'))}.{RESET}")
                action_history.append({
                    "command": cmd,
                    "state_changed": False,
                    "skipped": True
                })
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
                print(f"{YELLOW}[Repetition Skipped] Command {cmd.get('type')} on {cmd.get('target')} was previously ineffective — skipping, not aborting batch.{RESET}")
                action_history.append({
                    "command": cmd,
                    "state_changed": False,
                    "blocked": True
                })
                consecutive_ineffective += 1
                step_count += 1
                continue  # Skip this command but keep executing the rest of the batch

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
                    success = await self.bridge.call_action(cmd["target"], cmd.get("args", []))
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
                # If this was a navigation click, give React extra time to render the new page
                # and for the bridge to receive updated interactiveElements via registryDelta
                if cmd.get("type") == "dispatchEvent" and cmd.get("event") == "click":
                    await asyncio.sleep(0.5)
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
                    cleaned_after = {}
                    for k_after, val_after in values_after.items():
                        if "." in k_after:
                            comp_after, slot_after = k_after.rsplit(".", 1)
                            comp_after_clean = comp_after.split("#", 1)[0]
                            cleaned_after[f"{comp_after_clean}.{slot_after}"] = val_after
                        else:
                            cleaned_after[k_after] = val_after

                    for k, val in step.post_state_snapshot.items():
                        if "." in k:
                            comp_k, slot_k = k.rsplit(".", 1)
                            comp_k_clean = comp_k.split("#", 1)[0]
                            cleaned_key = f"{comp_k_clean}.{slot_k}"
                        else:
                            cleaned_key = k

                        if cleaned_key in cleaned_after:
                            if cleaned_after[cleaned_key] != val:
                                mismatch = True
                                break
                        else:
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

        # Sleep to allow React to render any final updates and WebSocket messages to be processed
        await asyncio.sleep(0.5)

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

        # Wait up to 3 seconds for the component registry to populate/synchronize
        start_wait = time.time()
        while not self.bridge.graph.get_mounted_components() and (time.time() - start_wait) < 3.0:
            await asyncio.sleep(0.1)

        # Decompose the high-level goal into sequential stages
        print(f"{CYAN}Decomposing high-level goal into sequential stages...{RESET}")
        stages = await self._decompose_goal(query)
        print(f"{GREEN}Decomposed into {len(stages)} stages:{RESET}")
        for idx, stage in enumerate(stages):
            print(f"  {idx+1}. {stage}")

        # Initialize global tracking variables across all stages
        global_action_history = []
        global_step_count = 0
        global_llm_calls_made = 0
        active_trace = None
        trace_step_index = 0

        # Execute each stage sequentially
        for idx, stage_query in enumerate(stages):
            print(f"\n{MAGENTA}===================================================={RESET}")
            print(f"{MAGENTA}[Stage {idx+1}/{len(stages)}] Starting: {stage_query}{RESET}")
            print(f"{MAGENTA}===================================================={RESET}")

            # Get fresh snapshot to compile the goal for this stage
            snapshot = self.bridge.graph.snapshot()
            try:
                goal = await self.bridge.llm_adapter.compile_goal(stage_query, snapshot)
                print(f"{GREEN}Successfully compiled sub-goal for stage {idx+1}!{RESET}")
                print(f"  Description: {goal.description}")
                print(f"  Success Conditions:")
                for cond in goal.success_conditions:
                    print(f"    - {cond.target} {cond.operator} {cond.value}")
            except Exception as e:
                print(f"{RED}Failed to compile goal for stage {idx+1}: {e}{RESET}")
                return {"status": "failed", "error": f"Failed to compile stage {idx+1}: {e}"}

            goal.max_steps = self.max_steps

            # Build state for the stage, carrying over historical values
            live_values = self._get_values_dict()
            state: AgentState = {
                "query": stage_query,
                "goal": goal,
                "registry": snapshot,
                "values": live_values,
                "commands": [],
                "action_history": global_action_history,
                "consecutive_ineffective_count": 0,
                "step_count": global_step_count,
                "status": "init",
                "error": None,
                "active_trace": active_trace,
                "trace_step_index": trace_step_index,
                "initial_values": live_values,
                "llm_calls_made": global_llm_calls_made
            }

            # Run the workflow for this stage
            result = await self.graph.ainvoke(state, config={"recursion_limit": 100})

            # Update global tracking variables
            global_action_history = result.get("action_history", [])
            global_step_count = result.get("step_count", 0)
            global_llm_calls_made = result.get("llm_calls_made", 0)
            active_trace = result.get("active_trace")
            trace_step_index = result.get("trace_step_index", 0)

            # Verify if this stage's success conditions are satisfied
            success_met = True
            for cond in goal.success_conditions:
                if not cond.evaluate(self.bridge.graph):
                    success_met = False
                    break

            if not success_met:
                print(f"\n{RED}[Failure] Stage {idx+1} failed to satisfy success conditions!{RESET}")
                if "action_history" in result:
                    print("Sequence of actions in this stage:")
                    for action_idx, item in enumerate(result["action_history"]):
                        print(f"  {action_idx+1}. Command: {json.dumps(item['command'])} | State Changed: {item['state_changed']}")
                await self.bridge.set_agent_status("failed")
                return {
                    "status": "failed",
                    "error": f"Stage {idx+1} success conditions not met",
                    "step_count": global_step_count,
                    "action_history": global_action_history
                }

            print(f"{GREEN}[Success] Stage {idx+1} accomplished!{RESET}")
            # Sleep a bit to let any unmounts/mounts settle before starting the next stage
            await asyncio.sleep(0.5)

        # All stages completed successfully!
        print(f"\n{GREEN}[Success] All stages completed successfully! Total steps: {global_step_count}{RESET}")
        await self.bridge.set_agent_status("succeeded")

        # Handle Golden Trace recording
        try:
            from react_agent_bridge.discovery.traces import GoldenTraceStore
            store = GoldenTraceStore(self.db_path)
            if active_trace:
                store.update_trace_confidence(active_trace.trace_id, succeeded=True)
            else:
                valid_steps = [h for h in global_action_history if not h.get("blocked")]
                if valid_steps:
                    import uuid
                    import hashlib
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
                    
                    mounted = self.bridge.graph.get_mounted_components()
                    names = sorted([c.display_name for c in mounted])
                    app_version_hash = hashlib.md5(json.dumps(names).encode("utf-8")).hexdigest()[:16]

                    sig = self._compute_goal_signature(goal)
                    
                    full_trace = GoldenTrace(
                        trace_id=str(uuid.uuid4()),
                        workflow_name=goal.description,
                        goal_description=query,
                        recorded_at=time.time(),
                        application_version_hash=app_version_hash,
                        precondition_state=global_action_history[0]["pre_state"] if global_action_history else {},
                        steps=steps,
                        postcondition_state=self._get_values_dict(),
                        execution_time_ms=0.0,
                        llm_calls_made=global_llm_calls_made,
                        confidence=1.0,
                        structural_signature=sig
                    )
                    store.record_trace(full_trace)
                    print(f"{GREEN}[Trace Replay] Successfully recorded new golden trace (ID: {full_trace.trace_id}){RESET}")
        except Exception as e:
            logger.error(f"Failed to record/update trace: {e}", exc_info=True)

        return {
            "status": "executed",
            "step_count": global_step_count,
            "action_history": global_action_history,
            "llm_calls_made": global_llm_calls_made
        }