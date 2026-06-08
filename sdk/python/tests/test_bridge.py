import asyncio
import pytest
from react_agent_bridge.core.futures import CommandFutureManager
from react_agent_bridge.core.exceptions import ConnectionLostError, CommandTimeoutError
from react_agent_bridge.core.graph.state_graph import ApplicationStateGraph
from react_agent_bridge.core.models import RegistryDeltaMessage, SerializedComponentEntry, SerializedStateSlot
from react_agent_bridge.core.rules.engine import RulesEngine
from react_agent_bridge.core.rules.registry import RuleRegistry
from react_agent_bridge.core.rules.result import RuleViolation


@pytest.mark.asyncio
async def test_command_future_correlation():
    manager = CommandFutureManager()
    cmd_id, fut = manager.create_future()
    
    # Assert correlation
    assert cmd_id in manager._pending
    
    # Resolve and assert outcome
    manager.resolve_future(cmd_id, {"success": True, "value": "test_val"})
    assert fut.done()
    res = await fut
    assert res["success"] is True
    assert res["value"] == "test_val"


@pytest.mark.asyncio
async def test_command_future_reject_all():
    manager = CommandFutureManager()
    _, fut1 = manager.create_future()
    _, fut2 = manager.create_future()
    
    manager.reject_all("Disconnecting")
    
    assert len(manager._pending) == 0
    with pytest.raises(ConnectionLostError) as exc_info:
        await fut1
    assert "Disconnecting" in str(exc_info.value)
    
    with pytest.raises(ConnectionLostError):
        await fut2


def test_state_graph_reconstruction():
    graph = ApplicationStateGraph()
    
    # Send a delta addition
    slot = SerializedStateSlot(key="count", hookIndex=0, sensitive=False)
    comp = SerializedComponentEntry(
        id="CounterComponent#1",
        displayName="CounterComponent",
        mountedAt=1000,
        route="/home",
        stateSlots=[slot]
    )
    
    delta = RegistryDeltaMessage(added=[comp], removed=[], updated=[])
    graph.apply_delta(delta)
    
    # Verify graph node mounted
    assert "CounterComponent#1" in graph.components
    node = graph.components["CounterComponent#1"]
    assert node.display_name == "CounterComponent"
    assert "count" in node.state_slots
    assert node.state_slots["count"].value is None

    # Apply live state snapshot update
    graph.update_state_value("CounterComponent#1.count", 42)
    assert graph.get_slot_value("CounterComponent#1.count") == 42


def test_rules_engine_preflight():
    registry = RuleRegistry()
    engine = RulesEngine(registry)
    graph = ApplicationStateGraph()

    # Mount the components and slots first to pass target mounted and slot exists checks
    slot_allowed = SerializedStateSlot(key="slot", hookIndex=0)
    slot_forbidden = SerializedStateSlot(key="slot", hookIndex=1)
    
    comp_allowed = SerializedComponentEntry(
        id="Allowed", displayName="Allowed", mountedAt=100, route="/", stateSlots=[slot_allowed]
    )
    comp_forbidden = SerializedComponentEntry(
        id="Forbidden", displayName="Forbidden", mountedAt=101, route="/", stateSlots=[slot_forbidden]
    )
    
    graph.apply_delta(RegistryDeltaMessage(added=[comp_allowed, comp_forbidden], removed=[], updated=[]))

    # Define a custom rule function
    def custom_rule(command: dict, state_graph: ApplicationStateGraph):
        if command.get("target") == "Forbidden.slot":
            return RuleViolation(
                rule_name="ForbiddenRule",
                message="Writing to Forbidden.slot is prohibited.",
                target="Forbidden.slot"
            )
        return None

    registry.add_rule(custom_rule, priority=200)

    # Valid command
    valid_cmd = {"type": "setState", "target": "Allowed.slot", "value": 10}
    res_valid = engine.evaluate(valid_cmd, graph)
    assert res_valid.valid is True

    # Invalid command matching custom rule
    invalid_cmd = {"type": "setState", "target": "Forbidden.slot", "value": 20}
    res_invalid = engine.evaluate(invalid_cmd, graph)
    assert res_invalid.valid is False
    assert len(res_invalid.violations) == 1
    assert res_invalid.violations[0].rule_name == "ForbiddenRule"


def test_writeable_slot_rule():
    from react_agent_bridge.core.rules.registry import RuleRegistry
    from react_agent_bridge.core.rules.engine import RulesEngine
    from react_agent_bridge.core.graph.state_graph import ApplicationStateGraph
    from react_agent_bridge.core.models import SerializedStateSlot, SerializedComponentEntry, RegistryDeltaMessage

    registry = RuleRegistry()
    engine = RulesEngine(registry)
    graph = ApplicationStateGraph()

    slot_user = SerializedStateSlot(key="secretKey", hookIndex=0, writeable="user")
    slot_both = SerializedStateSlot(key="operatingMode", hookIndex=1, writeable="both")

    comp = SerializedComponentEntry(
        id="App#r1", displayName="App", mountedAt=100, route="/", stateSlots=[slot_user, slot_both]
    )

    graph.apply_delta(RegistryDeltaMessage(added=[comp], removed=[], updated=[]))

    # Command setting user-writable only slot -> should be blocked by WriteableSlotRule
    invalid_cmd = {"type": "setState", "target": "App#r1.secretKey", "value": "new-secret"}
    res_invalid = engine.evaluate(invalid_cmd, graph)
    assert res_invalid.valid is False
    assert len(res_invalid.violations) == 1
    assert res_invalid.violations[0].rule_name == "WriteableSlotRule"

    # Command setting both-writable slot -> should succeed
    valid_cmd = {"type": "setState", "target": "App#r1.operatingMode", "value": "boost"}
    res_valid = engine.evaluate(valid_cmd, graph)
    assert res_valid.valid is True


from react_agent_bridge.core.llm import BaseLLMAdapter, StructuredAction
from react_agent_bridge.core.planner.goal import Goal, GoalCondition
from react_agent_bridge.core.planner.planner import GoalDirectedPlanner


class MockLLMAdapter(BaseLLMAdapter):
    def __init__(self, action: StructuredAction = None, mock_goal: Goal = None):
        self.action = action
        self.mock_goal = mock_goal
        self.calls = []
        self.compile_calls = []

    async def call(self, prompt: str, tools: list, goal: Goal) -> StructuredAction:
        self.calls.append((prompt, tools, goal))
        return self.action

    async def compile_goal(self, query: str, registry_snapshot: dict) -> Goal:
        self.compile_calls.append((query, registry_snapshot))
        if self.mock_goal is not None:
            return self.mock_goal
        return Goal(description=query, success_conditions=[])


@pytest.mark.asyncio
async def test_goal_directed_planner_custom_adapter():
    # Setup mock adapter returning a set_state action
    action = StructuredAction(name="set_state", arguments={"target": "Allowed.slot", "value": 42})
    adapter = MockLLMAdapter(action)
    
    # Initialize a mock bridge/planner
    class MockBridge:
        def __init__(self):
            self.graph = ApplicationStateGraph()
            # Mount a mock component so pre-flight validation succeeds
            slot = SerializedStateSlot(key="slot", hookIndex=0)
            comp = SerializedComponentEntry(id="Allowed", displayName="Allowed", mountedAt=100, route="/", stateSlots=[slot])
            self.graph.apply_delta(RegistryDeltaMessage(added=[comp], removed=[], updated=[]))
            
            self.rules_engine = None
            self.business_logic_path = None
            self.llm_adapter = adapter
            self.commands_sent = []

        async def set_state(self, target: str, value) -> bool:
            self.commands_sent.append(("setState", target, value))
            self.graph.update_state_value(target, value)
            return True

    bridge = MockBridge()
    planner = GoalDirectedPlanner(bridge, llm_adapter=adapter)
    
    # Define success condition: state slot value equals 42
    goal = Goal(
        description="Set slot to 42",
        success_conditions=[
            GoalCondition(target="Allowed.slot", operator="equals", value=42)
        ],
        max_steps=5
    )
    
    # Execute the planner
    result = await planner.execute(goal)
    
    # Assert successful planning
    assert result.success is True
    assert len(adapter.calls) == 1
    assert len(bridge.commands_sent) == 1
    assert bridge.commands_sent[0] == ("setState", "Allowed.slot", 42)


@pytest.mark.asyncio
async def test_planner_intake_workflow():
    # Setup mock adapter with a mock goal returned by compile_goal
    mock_goal = Goal(description="Mock Goal", success_conditions=[])
    adapter = MockLLMAdapter(mock_goal=mock_goal)
    
    class MockBridge:
        def __init__(self):
            self.graph = ApplicationStateGraph()
            self.business_logic_path = None
            self.llm_adapter = adapter

    bridge = MockBridge()
    planner = GoalDirectedPlanner(bridge, llm_adapter=adapter)
    
    # Test intake falling back to LLM adapter
    res_goal = await planner.intake("Login with username agent_john")
    assert res_goal == mock_goal
    assert len(adapter.compile_calls) == 1
    assert adapter.compile_calls[0][0] == "Login with username agent_john"


from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_litellm_adapter_compile_goal_markdown_stripping():
    import os
    from react_agent_bridge.core.llm import LiteLLMAdapter
    
    mock_response = AsyncMock()
    mock_choice = AsyncMock()
    mock_choice.message.content = """```json
    {
        "description": "Log in to the system",
        "success_conditions": [
            {
                "target": "AuthStore.token",
                "operator": "truthy"
            }
        ],
        "failure_conditions": [],
        "max_steps": 10,
        "timeout_seconds": 30.0
    }
    ```"""
    mock_response.choices = [mock_choice]
    
    adapter = LiteLLMAdapter(model="gemini/gemma-4-31b-it")
    
    with patch.dict(os.environ, {"GEMINI_API_KEY": "mock-key"}):
        with patch("litellm.acompletion", return_value=mock_response) as mock_acompletion:
            goal = await adapter.compile_goal("Login with username agent_john", {})
            
            mock_acompletion.assert_called_once()
            assert goal.description == "Log in to the system"
            assert len(goal.success_conditions) == 1
            assert goal.success_conditions[0].target == "AuthStore.token"
            assert goal.success_conditions[0].operator == "truthy"
            assert goal.max_steps == 10
            assert goal.timeout_seconds == 30.0


def test_goal_condition_sensitive_redacted_evaluation():
    graph = ApplicationStateGraph()
    slot = SerializedStateSlot(key="token", hookIndex=0, sensitive=True)
    comp = SerializedComponentEntry(
        id="AuthStore",
        displayName="AuthStore",
        mountedAt=1000,
        route="/",
        stateSlots=[slot]
    )
    graph.apply_delta(RegistryDeltaMessage(added=[comp], removed=[], updated=[]))

    # Token is initially empty string: "" (which is falsy)
    graph.update_state_value("AuthStore.token", "")

    # Success Condition: token is truthy
    cond = GoalCondition(target="AuthStore.token", operator="truthy")

    # If evaluated against the graph directly (uses raw unredacted value):
    assert cond.evaluate(graph) is False

    # If evaluated against a snapshot (where empty sensitive value is NOT redacted to "[REDACTED]" yet):
    snapshot = graph.snapshot()
    assert snapshot["components"]["AuthStore"]["stateSlots"]["token"] == ""
    assert cond.evaluate(snapshot) is False

    # Now, update token to a real value (which is truthy)
    graph.update_state_value("AuthStore.token", "jwt_token_123")

    # If evaluated against the graph directly, it is now True:
    assert cond.evaluate(graph) is True

    # If evaluated against the snapshot (where populated sensitive value IS redacted to "[REDACTED]"):
    snapshot_after = graph.snapshot()
    assert snapshot_after["components"]["AuthStore"]["stateSlots"]["token"] == "[REDACTED]"
    assert cond.evaluate(snapshot_after) is True




