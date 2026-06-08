import asyncio
import logging
import time
import json
import os
from typing import Optional, Callable, List, Tuple
from react_agent_bridge.core.planner.goal import Goal, GoalCondition
from react_agent_bridge.core.planner.step import PlanStep, PlanResult
from react_agent_bridge.core.planner.verifier import PostConditionVerifier
from react_agent_bridge.core.transition.model import TransitionModel
from react_agent_bridge.business_logic.injector import BusinessLogicContext, BusinessLogicInjector
from react_agent_bridge.prompt.builder import build_prompt
from react_agent_bridge.core.llm import BaseLLMAdapter
from react_agent_bridge.integrations.openai import get_openai_tools

logger = logging.getLogger("react_agent_bridge.planner")


class GoalDirectedPlanner:
    """
    Main goal-directed reactive planning runtime execution engine.
    """
    def __init__(
        self,
        bridge,
        llm_call_fn: Optional[Callable[[str], dict]] = None,
        transition_model: Optional[TransitionModel] = None,
        business_context: Optional[BusinessLogicContext] = None,
        llm_adapter: Optional[BaseLLMAdapter] = None
    ):
        self.bridge = bridge
        self.llm_call_fn = llm_call_fn
        self.transition_model = transition_model
        self.business_context = business_context
        self.llm_adapter = llm_adapter or getattr(bridge, "llm_adapter", None)
        if not self.llm_adapter and not self.llm_call_fn:
            raise ValueError("No llm_adapter was provided on the planner or the bridge, and no llm_call_fn was configured.")

    async def intake(self, query: str) -> Goal:
        """
        Translates a natural language query into a structured Goal object.
        """
        snapshot = self.bridge.graph.snapshot()

        # 1. Try to resolve via predefined workflows first
        if self.bridge.business_logic_path and not self.business_context:
            from react_agent_bridge.business_logic.loader import BusinessLogicLoader
            from react_agent_bridge.business_logic.parser import BusinessLogicParser
            loader = BusinessLogicLoader(self.bridge.business_logic_path)
            try:
                doc_content = loader.load()
                doc = BusinessLogicParser.parse(doc_content)
                self.business_context = BusinessLogicInjector.select(
                    doc, 
                    route=self.bridge.graph.get_mounted_components()[0].route if self.bridge.graph.get_mounted_components() else None,
                    goal=None,
                    graph_snapshot=snapshot
                )
            except Exception as e:
                logger.error(f"Failed to load business logic context in intake: {e}")

        if self.business_context and self.business_context.workflows:
            query_lower = query.lower()
            for wf in self.business_context.workflows:
                if wf.name.lower() in query_lower or query_lower in wf.name.lower():
                    logger.info(f"Intake matched query to workflow definition: {wf.name}")
                    success_conds = [wf.success_condition] if wf.success_condition else []
                    failure_conds = [wf.failure_condition] if wf.failure_condition else []
                    return Goal(
                        description=wf.name,
                        success_conditions=success_conds,
                        failure_conditions=failure_conds
                    )

        # 2. Fall back to LLM adapter compilation
        if self.llm_adapter:
            logger.info(f"Compiling natural language goal dynamically: '{query}'")
            return await self.llm_adapter.compile_goal(query, snapshot)
        
        raise ValueError("No LLM adapter available to compile dynamic query.")

    async def _set_status(self, status: str):
        if hasattr(self.bridge, "set_agent_status"):
            await self.bridge.set_agent_status(status)

    async def execute(self, goal: Goal) -> PlanResult:
        """
        Executes the planning loop targeting the provided Goal.
        """
        history = []
        step_idx = 0
        start_time = time.time()
        
        logger.info(f"Starting Goal execution: {goal.description}")
        await self._set_status("working")

        while step_idx < goal.max_steps:
            # Check for timeout
            if time.time() - start_time > goal.timeout_seconds:
                logger.error("Planning loop timed out.")
                await self._set_status("failed")
                return PlanResult(success=False, steps_executed=step_idx, history=history, error_message="Execution timeout reached.")

            # 1. Take current snapshot and check conditions
            snapshot = self.bridge.graph.snapshot()

            # Check success conditions
            success_met = True
            for cond in goal.success_conditions:
                if not cond.evaluate(self.bridge.graph):
                    success_met = False
                    break
            if goal.success_conditions and success_met:
                logger.info("Goal success conditions met!")
                await self._set_status("succeeded")
                return PlanResult(success=True, steps_executed=step_idx, history=history)

            # Check failure conditions
            for cond in goal.failure_conditions:
                if cond.evaluate(self.bridge.graph):
                    logger.error(f"Goal failure condition triggered: {cond.target}")
                    await self._set_status("failed")
                    return PlanResult(success=False, steps_executed=step_idx, history=history, error_message=f"Failure condition triggered: {cond.target}")

            # 2. Select contextual business details
            if self.bridge.business_logic_path and not self.business_context:
                # Load context if not already done
                from react_agent_bridge.business_logic.loader import BusinessLogicLoader
                from react_agent_bridge.business_logic.parser import BusinessLogicParser
                loader = BusinessLogicLoader(self.bridge.business_logic_path)
                try:
                    doc_content = loader.load()
                    doc = BusinessLogicParser.parse(doc_content)
                    self.business_context = BusinessLogicInjector.select(
                        doc, 
                        route=self.bridge.graph.get_mounted_components()[0].route if self.bridge.graph.get_mounted_components() else None,
                        goal=goal,
                        graph_snapshot=snapshot
                    )
                except Exception as e:
                    logger.error(f"Failed to load business logic context: {e}")

            # 3. Assemble the prompt (including planning feedback error if replanning)
            prompt = build_prompt(self.business_context, snapshot, goal)

            # 4. Invoke LLM to choose next command (supporting up to 3 replanning attempts if rules reject command)
            cmd = None
            replanning_errors = []
            
            for attempt in range(3):
                attempt_prompt = prompt
                if replanning_errors:
                    attempt_prompt += f"\n\n[Warning] Previous attempt failed validation: {replanning_errors[-1]}. Please choose a different action or parameters."

                try:
                    if self.llm_adapter:
                        tools = get_openai_tools()
                        tool_call = await self.llm_adapter.call(attempt_prompt, tools, goal)
                        tool_call_dict = {
                            "name": tool_call.name,
                            "arguments": tool_call.arguments
                        }
                    elif self.llm_call_fn:
                        tool_call_dict = self.llm_call_fn(attempt_prompt)
                    else:
                        raise ValueError("No LLM adapter or call function was configured.")
                    
                    # Convert tool call to command dictionary
                    cmd = self._tool_call_to_command(tool_call_dict)
                except Exception as e:
                    logger.error(f"LLM generation failed: {e}")
                    await self._set_status("failed")
                    return PlanResult(success=False, steps_executed=step_idx, history=history, error_message=f"LLM error: {e}")

                # 5. Pre-flight check rules engine
                if self.bridge.rules_engine:
                    res = self.bridge.rules_engine.evaluate(cmd, self.bridge.graph)
                    if not res.valid:
                        err_msg = res.violations[0].message
                        replanning_errors.append(err_msg)
                        logger.warning(f"Rules engine blocked proposed action (attempt {attempt+1}): {err_msg}")
                        cmd = None
                        continue
                
                # Command passed validation
                break

            if not cmd:
                # Loop failed to find a valid action
                await self._set_status("failed")
                return PlanResult(
                    success=False,
                    steps_executed=step_idx,
                    history=history,
                    error_message=f"Pre-flight rules validation rejected actions: {replanning_errors}"
                )

            # 6. Execute the command
            state_before = self.bridge.graph.snapshot()
            self.bridge.graph.by_agent = True
            
            t_start = time.time()
            ack_success = False
            error_message = None

            try:
                if cmd["type"] == "setState":
                    ack_success = await self.bridge.set_state(cmd["target"], cmd["value"])
                elif cmd["type"] == "dispatchEvent":
                    ack_success = await self.bridge.dispatch_event(cmd["target"], cmd["event"], cmd.get("payload"))
                elif cmd["type"] == "callAction":
                    ack_success = await self.bridge.call_action(cmd["target"], cmd["args"])
                elif cmd["type"] == "waitFor":
                    cond = cmd["condition"]
                    ack_success = await self.bridge.wait_for(
                        cmd["target"],
                        cond["operator"],
                        cond.get("value"),
                        timeout_ms=cmd.get("timeoutMs", 5000)
                    )
            except Exception as e:
                error_message = str(e)
                logger.error(f"Command execution error: {e}")

            # Sleep briefly to ensure rendering settling commits have fully updated local graph cache
            await asyncio.sleep(0.15)
            self.bridge.graph.by_agent = False
            t_end = time.time()

            state_after = self.bridge.graph.snapshot()
            time_taken_ms = (t_end - t_start) * 1000.0

            # 7. Post-condition verification
            verified = PostConditionVerifier.verify(cmd, state_before, state_after, ack_success)

            # 8. Record transition
            if self.transition_model:
                try:
                    self.transition_model.record_transition(
                        command=cmd,
                        state_before=state_before,
                        state_after=state_after,
                        ack_success=ack_success,
                        time_to_settle_ms=time_taken_ms
                    )
                except Exception as e:
                    logger.error(f"Failed to record transition observation: {e}")

            # Record step in plan history
            step = PlanStep(
                step_index=step_idx,
                command=cmd,
                rule_check_passed=True,
                ack_success=ack_success,
                post_condition_verified=verified,
                time_taken_ms=time_taken_ms,
                error_message=error_message
            )
            history.append(step)
            step_idx += 1

        await self._set_status("failed")
        return PlanResult(success=False, steps_executed=step_idx, history=history, error_message="Max execution steps exceeded.")

    def _tool_call_to_command(self, tool_call: dict) -> dict:
        """Helper to map standard tool outputs to protocol dictionary commands."""
        name = tool_call["name"]
        args = tool_call["arguments"]

        if name == "set_state":
            return {
                "type": "setState",
                "target": args["target"],
                "value": args["value"]
            }
        elif name == "dispatch_event":
            cmd = {
                "type": "dispatchEvent",
                "target": args["target"],
                "event": args["event"]
            }
            if "payload" in args:
                cmd["payload"] = args["payload"]
            return cmd
        elif name == "call_action":
            return {
                "type": "callAction",
                "target": args["target"],
                "args": args["args"]
            }
        elif name == "wait_for":
            cond = {"operator": args["operator"]}
            if "value" in args:
                cond["value"] = args["value"]
            return {
                "type": "waitFor",
                "target": args["target"],
                "condition": cond,
                "timeoutMs": args.get("timeout_ms", 5000)
            }
        else:
            raise ValueError(f"Unknown tool name: {name}")
