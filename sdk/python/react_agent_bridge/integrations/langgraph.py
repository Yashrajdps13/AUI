from typing import Optional, List, Dict, Any


def build_agent(bridge, llm_client, business_context: Optional[str] = None) -> Any:
    """
    Assembles a LangGraph state graph linking the ReactAgentBridge WebSocket interface
    to agent executors. Requires langgraph to be installed.
    """
    try:
        from typing_extensions import TypedDict
        from langgraph.graph import StateGraph, END
    except ImportError:
        raise ImportError(
            "langgraph and typing_extensions are required to use build_agent. "
            "Please install them using: pip install langgraph typing_extensions"
        )

    from react_agent_bridge.core.planner.goal import Goal, GoalCondition
    from react_agent_bridge.core.planner.verifier import PostConditionVerifier
    from react_agent_bridge.prompt.builder import build_prompt

    # Define State schema
    class AgentState(TypedDict):
        query: str
        goal: Optional[Goal]
        graph_snapshot: dict
        proposed_command: Optional[dict]
        replanning_errors: List[str]
        step_count: int
        success: bool
        error: Optional[str]

    # Node 1: Intake query and compile structured Goal
    def intake_node(state: AgentState) -> dict:
        query = state["query"]
        logger_name = "react_agent_bridge.integrations.langgraph"
        import logging
        logger = logging.getLogger(logger_name)
        logger.info(f"LangGraph intake query: {query}")
        
        # In a real environment, we'd compile the query into a Goal.
        # Here we create a basic fallback Goal.
        goal = Goal(description=query)
        return {
            "goal": goal,
            "graph_snapshot": bridge.graph.snapshot(),
            "replanning_errors": [],
            "step_count": 0,
            "success": False,
            "error": None
        }

    # Node 2: Prompt LLM and propose next command
    def plan_node(state: AgentState) -> dict:
        goal = state["goal"]
        snapshot = bridge.graph.snapshot()
        
        # Load and assemble system prompt
        prompt = build_prompt(None, snapshot, goal)
        if state["replanning_errors"]:
            prompt += f"\n\n[Warning] Previous action failed: {state['replanning_errors'][-1]}"

        # Invoke model function (llm_client should act as a callable prompt compiler returning a tool dict)
        tool_call = llm_client(prompt)
        
        # Convert tool call to command
        from react_agent_bridge.core.planner.planner import GoalDirectedPlanner
        planner_helper = GoalDirectedPlanner(bridge)
        cmd = planner_helper._tool_call_to_command(tool_call)

        return {"proposed_command": cmd, "graph_snapshot": snapshot}

    # Node 3: Rules validate, dispatch, wait, verify, transition update
    async def execute_node(state: AgentState) -> dict:
        cmd = state["proposed_command"]
        snapshot_before = state["graph_snapshot"]
        errors = list(state.get("replanning_errors", []))

        # Pre-flight rule validation
        if bridge.rules_engine:
            res = bridge.rules_engine.evaluate(cmd, bridge.graph)
            if not res.valid:
                errors.append(res.violations[0].message)
                return {"replanning_errors": errors, "proposed_command": None}

        # Dispatch command
        success = False
        t_start = time.time()
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
            errors.append(str(e))
            return {"replanning_errors": errors, "proposed_command": None}
        finally:
            import asyncio
            await asyncio.sleep(0.15)
            bridge.graph.by_agent = False

        # Post-condition verification
        snapshot_after = bridge.graph.snapshot()
        verified = PostConditionVerifier.verify(cmd, snapshot_before, snapshot_after, success)
        
        if not verified:
            errors.append("Action executed but expected post-condition was not met.")
            return {"replanning_errors": errors, "proposed_command": None}

        # Evaluate if goal is met
        goal = state["goal"]
        goal_met = True
        for cond in goal.success_conditions:
            if not cond.evaluate(bridge.graph):
                goal_met = False
                break

        return {
            "graph_snapshot": snapshot_after,
            "step_count": state["step_count"] + 1,
            "success": goal_met if goal.success_conditions else True,
            "replanning_errors": []
        }

    # Setup routing helper
    def should_continue(state: AgentState):
        if state["success"]:
            return END
        if state["step_count"] >= 15:
            return END
        # If command was rejected by validation/execution, replan
        if not state["proposed_command"]:
            return "planner"
        return "planner"

    import time
    # Construct workflow
    workflow = StateGraph(AgentState)
    workflow.add_node("intake", intake_node)
    workflow.add_node("planner", plan_node)
    workflow.add_node("executor", execute_node)

    workflow.set_entry_point("intake")
    workflow.add_edge("intake", "planner")
    workflow.add_edge("planner", "executor")
    
    workflow.add_conditional_edges(
        "executor",
        should_continue,
        {
            "planner": "planner",
            END: END
        }
    )

    return workflow.compile()
