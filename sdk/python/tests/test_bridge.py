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


def test_agent_runner_init_and_compilation():
    from react_agent_bridge import ReactAgentBridge, AgentRunner
    
    bridge = ReactAgentBridge(host="localhost", port=8000)
    runner = AgentRunner(bridge, model="ollama/qwen2.5:7b", max_steps=15)
    
    assert runner.model == "ollama/qwen2.5:7b"
    assert runner.max_steps == 15
    assert runner.graph is not None


def test_goal_condition_component_id_matching():
    graph = ApplicationStateGraph()
    slot = SerializedStateSlot(key="isSubmitted", hookIndex=0)
    comp = SerializedComponentEntry(
        id="App#r9",
        displayName="App",
        mountedAt=1000,
        route="/",
        stateSlots=[slot]
    )
    graph.apply_delta(RegistryDeltaMessage(added=[comp], removed=[], updated=[]))
    graph.update_state_value("App#r9.isSubmitted", True)

    cond = GoalCondition(target="App.isSubmitted", operator="equals", value=True)
    assert cond.evaluate(graph) is True

    snapshot = graph.snapshot()
    assert cond.evaluate(snapshot) is True


def test_cli_llm_resolution():
    import os
    from unittest.mock import patch
    from react_agent_bridge.cli import resolve_and_check_llm

    # Test config file model fallback and key export
    mock_config = {
        "model": "openai/gpt-4o",
        "api_keys": {
            "OPENAI_API_KEY": "test-openai-key"
        }
    }
    
    with patch("react_agent_bridge.cli.load_config", return_value=mock_config):
        with patch.dict(os.environ, {}, clear=True):
            model = resolve_and_check_llm(explicit_model=None)
            assert model == "openai/gpt-4o"
            assert os.environ.get("OPENAI_API_KEY") == "test-openai-key"


def test_cli_argument_resolution_priority():
    import os
    from unittest.mock import patch
    from react_agent_bridge.cli import resolve_and_check_llm

    mock_config = {"model": "ollama/qwen2.5:7b"}

    with patch("react_agent_bridge.cli.load_config", return_value=mock_config):
        # Env var priority over config file
        with patch.dict(os.environ, {"REACT_AGENT_BRIDGE_MODEL": "groq/llama3", "GROQ_API_KEY": "groq-key"}):
            model = resolve_and_check_llm(explicit_model=None)
            assert model == "groq/llama3"

        # Explicit model flag priority over env var and config
        with patch.dict(os.environ, {"REACT_AGENT_BRIDGE_MODEL": "groq/llama3", "GROQ_API_KEY": "groq-key", "GEMINI_API_KEY": "gemini-key"}):
            model = resolve_and_check_llm(explicit_model="gemini/gemini-1.5-flash")
            assert model == "gemini/gemini-1.5-flash"


@pytest.mark.asyncio
async def test_safe_subscribe_handles_exceptions():
    from react_agent_bridge.core.client import ReactAgentBridge
    from react_agent_bridge.core.exceptions import RuleViolationError
    from react_agent_bridge.core.models import RegistryDeltaMessage, SerializedComponentEntry
    from unittest.mock import AsyncMock

    bridge = ReactAgentBridge(host="localhost", port=8000)
    
    # Mock self.subscribe to raise a RuleViolationError (as would happen in validation race condition)
    bridge.subscribe = AsyncMock(side_effect=RuleViolationError("Validation failed"))
    
    # Pre-populate graph so component check passes
    comp = SerializedComponentEntry(id="DashboardView#r9", displayName="DashboardView", mountedAt=1000, route="/")
    bridge.graph.apply_delta(RegistryDeltaMessage(added=[comp], removed=[], updated=[]))
    
    # Call _safe_subscribe and verify it handles the error gracefully without raising
    await bridge._safe_subscribe("DashboardView#r9")
    
    bridge.subscribe.assert_called_once_with("DashboardView#r9")


@pytest.mark.asyncio
async def test_execute_node_sanitizer_rejection():
    from react_agent_bridge.core.client import ReactAgentBridge
    from react_agent_bridge.core.planner.runner import AgentRunner
    from react_agent_bridge.core.planner.goal import Goal
    
    bridge = ReactAgentBridge(host="localhost", port=8000)
    runner = AgentRunner(bridge, model="mock-model")
    
    # State has no mounted components, so allowed sets will be empty.
    # Proposing a setState command should trigger a sanitizer rejection.
    state = {
        "query": "Set slot to 42",
        "goal": Goal(description="Set slot to 42", success_conditions=[]),
        "registry": {},
        "values": {},
        "commands": [{"type": "setState", "target": "SomeComponent.slot", "value": 42}],
        "action_history": [],
        "consecutive_ineffective_count": 0,
        "step_count": 0,
        "active_trace": None,
        "trace_step_index": 0
    }
    
    result = await runner._execute_node(state)
    
    assert result["consecutive_ineffective_count"] == 1
    assert result["step_count"] == 1
    assert len(result["action_history"]) == 1
    assert result["action_history"][0]["rejected"] is True
    assert "Command rejected" in result["action_history"][0]["error"]


@pytest.mark.asyncio
async def test_plan_node_stuck_warnings_rejection():
    from react_agent_bridge.core.client import ReactAgentBridge
    from react_agent_bridge.core.planner.runner import AgentRunner
    from react_agent_bridge.core.planner.goal import Goal
    from unittest.mock import patch
    
    bridge = ReactAgentBridge(host="localhost", port=8000)
    runner = AgentRunner(bridge, model="mock-model")
    
    # Simulate a history with 3 consecutive rejections for the same target
    history = [
        {"command": {"type": "setState", "target": "LoginView#r5.password", "value": "secret"}, "rejected": True, "error": "Command rejected: target LoginView#r5.password is not in the registry"},
        {"command": {"type": "setState", "target": "LoginView#r5.password", "value": "secret"}, "rejected": True, "error": "Command rejected: target LoginView#r5.password is not in the registry"},
        {"command": {"type": "setState", "target": "LoginView#r5.password", "value": "secret"}, "rejected": True, "error": "Command rejected: target LoginView#r5.password is not in the registry"},
    ]
    
    state = {
        "query": "Log in",
        "goal": Goal(description="Log in", success_conditions=[]),
        "registry": {},
        "values": {},
        "commands": [],
        "action_history": history,
        "consecutive_ineffective_count": 3,
        "step_count": 3,
        "active_trace": None,
        "trace_step_index": 0,
        "llm_calls_made": 0
    }
    
    # We patch litellm.completion to return a mock response
    from unittest.mock import MagicMock
    mock_res = MagicMock()
    mock_res.choices = [MagicMock(message=MagicMock(content="[]"))]
    
    with patch("litellm.completion", return_value=mock_res) as mock_complete:
        res = runner._plan_node(state)
        
        # Verify call arguments
        called_args = mock_complete.call_args[1]
        messages = called_args["messages"]
        system_content = messages[0]["content"]
        
        # The warning should be included in the system prompt
        assert "WARNING: The command target 'LoginView#r5.password' was rejected" in system_content
        assert "You MUST read the COMPONENT REGISTRY and CURRENT STATE VALUES" in system_content


@pytest.mark.asyncio
async def test_execute_node_wait_for_console_logs_rejection():
    from react_agent_bridge.core.client import ReactAgentBridge
    from react_agent_bridge.core.planner.runner import AgentRunner
    from react_agent_bridge.core.planner.goal import Goal
    
    bridge = ReactAgentBridge(host="localhost", port=8000)
    runner = AgentRunner(bridge, model="mock-model")
    
    state = {
        "query": "Wait for consoleLogs",
        "goal": Goal(description="Wait for consoleLogs", success_conditions=[]),
        "registry": {},
        "values": {},
        "commands": [{"type": "waitFor", "target": "Layout.consoleLogs", "condition": {"operator": "changed"}}],
        "action_history": [],
        "consecutive_ineffective_count": 0,
        "step_count": 0,
        "active_trace": None,
        "trace_step_index": 0
    }
    
    result = await runner._execute_node(state)
    
    assert result["consecutive_ineffective_count"] == 1
    assert result["step_count"] == 1
    assert len(result["action_history"]) == 1
    assert result["action_history"][0]["rejected"] is True
    assert "contains a debug ledger or log field" in result["action_history"][0]["error"]


@pytest.mark.asyncio
async def test_litellm_adapter_compile_goal_retry_feedback():
    import os
    from react_agent_bridge.core.llm import LiteLLMAdapter
    from unittest.mock import AsyncMock, patch
    
    # First mock choice returns a schema with "LoginView.error" as success condition (invalid target)
    mock_choice_1 = AsyncMock()
    mock_choice_1.message.content = """```json
    {
        "description": "Log in",
        "success_conditions": [
            {
                "target": "LoginView.error",
                "operator": "equals",
                "value": ""
            }
        ],
        "failure_conditions": [],
        "max_steps": 10,
        "timeout_seconds": 30.0
    }
    ```"""
    
    # Second mock choice returns a schema with "AuthStore.isAuthenticated" (valid target)
    mock_choice_2 = AsyncMock()
    mock_choice_2.message.content = """```json
    {
        "description": "Log in",
        "success_conditions": [
            {
                "target": "AuthStore.isAuthenticated",
                "operator": "equals",
                "value": true
            }
        ],
        "failure_conditions": [],
        "max_steps": 10,
        "timeout_seconds": 30.0
    }
    ```"""
    
    # Mock responses sequentially
    mock_response_1 = AsyncMock()
    mock_response_1.choices = [mock_choice_1]
    
    mock_response_2 = AsyncMock()
    mock_response_2.choices = [mock_choice_2]
    
    adapter = LiteLLMAdapter(model="gemini/gemma-4-31b-it")
    
    with patch.dict(os.environ, {"GEMINI_API_KEY": "mock-key"}):
        with patch("litellm.acompletion", side_effect=[mock_response_1, mock_response_2]) as mock_acompletion:
            # Registry contains AuthStore.isAuthenticated and LoginView.error
            registry_snapshot = {
                "components": {
                    "AuthStore": {
                        "stateSlots": {"isAuthenticated": False}
                    },
                    "LoginView": {
                        "stateSlots": {"error": ""}
                    }
                }
            }
            goal = await adapter.compile_goal("Login", registry_snapshot)
            
            # acompletion should be called twice (the first attempt failed validation and retried)
            assert mock_acompletion.call_count == 2
            assert goal.description == "Log in"
            assert len(goal.success_conditions) == 1
            assert goal.success_conditions[0].target == "AuthStore.isAuthenticated"
            assert goal.success_conditions[0].operator == "equals"
            assert goal.success_conditions[0].value is True


def test_target_mounted_rule_call_action():
    from react_agent_bridge.core.rules.registry import RuleRegistry
    from react_agent_bridge.core.rules.engine import RulesEngine
    from react_agent_bridge.core.graph.state_graph import ApplicationStateGraph
    from react_agent_bridge.core.models import SerializedComponentEntry, RegistryDeltaMessage
    from react_agent_bridge.core.rules.base_rules import target_mounted_rule

    registry = RuleRegistry()
    registry.add_rule(target_mounted_rule)
    engine = RulesEngine(registry)
    graph = ApplicationStateGraph()

    comp = SerializedComponentEntry(
        id="ZustandStore#AuthStore", displayName="AuthStore", mountedAt=100, route="/", stateSlots=[], actions=["loginAction"]
    )
    graph.apply_delta(RegistryDeltaMessage(added=[comp], removed=[], updated=[]))

    # A callAction command targeting ZustandStore#AuthStore.loginAction
    cmd = {
        "type": "callAction",
        "target": "ZustandStore#AuthStore.loginAction",
        "args": []
    }

    res = engine.evaluate(cmd, graph)
    assert res.valid is True


@pytest.mark.asyncio
async def test_plan_node_json_repair_reconstruction():
    from react_agent_bridge.core.client import ReactAgentBridge
    from react_agent_bridge.core.planner.runner import AgentRunner
    from react_agent_bridge.core.planner.goal import Goal
    from unittest.mock import patch, MagicMock

    bridge = ReactAgentBridge(host="localhost", port=8000)
    runner = AgentRunner(bridge, model="mock-model")

    state = {
        "query": "Click button",
        "goal": Goal(description="Click button", success_conditions=[]),
        "registry": {},
        "values": {},
        "commands": [],
        "action_history": [],
        "consecutive_ineffective_count": 0,
        "step_count": 0,
        "active_trace": None,
        "trace_step_index": 0,
        "llm_calls_made": 0
    }

    # 1. Unescaped quotes inside string element: ["{"type":"dispatchEvent", ...}"]
    mock_res_1 = MagicMock()
    mock_res_1.choices = [MagicMock(message=MagicMock(content='["{"type":"dispatchEvent","target":"DashboardView#r9","event":"click","payload":"#link-project-proj-1"}"]'))]

    with patch("litellm.completion", return_value=mock_res_1):
        res1 = runner._plan_node(state)
        assert res1["status"] == "planned"
        assert len(res1["commands"]) == 1
        assert res1["commands"][0]["type"] == "dispatchEvent"
        assert res1["commands"][0]["payload"] == "#link-project-proj-1"

    # 2. Escaped quotes parsing to a string: ["{\"type\":\"dispatchEvent\", ...}"]
    mock_res_2 = MagicMock()
    mock_res_2.choices = [MagicMock(message=MagicMock(content='["{\\"type\\":\\"dispatchEvent\\",\\"target\\":\\"DashboardView#r9\\",\\"event\\":\\"click\\",\\"payload\\":\\"#link-project-proj-1\\"}"]'))]

    with patch("litellm.completion", return_value=mock_res_2):
        res2 = runner._plan_node(state)
        assert res2["status"] == "planned"
        assert len(res2["commands"]) == 1
        assert res2["commands"][0]["type"] == "dispatchEvent"
        assert res2["commands"][0]["payload"] == "#link-project-proj-1"


@pytest.mark.asyncio
async def test_runner_system_prompt_rule_12():
    from react_agent_bridge.core.client import ReactAgentBridge
    from react_agent_bridge.core.planner.runner import AgentRunner
    from react_agent_bridge.core.planner.goal import Goal
    from unittest.mock import patch, MagicMock

    bridge = ReactAgentBridge(host="localhost", port=8000)
    runner = AgentRunner(bridge, model="mock-model")

    state = {
        "query": "Click button",
        "goal": Goal(description="Click button", success_conditions=[]),
        "registry": {},
        "values": {},
        "commands": [],
        "action_history": [],
        "consecutive_ineffective_count": 0,
        "step_count": 0,
        "active_trace": None,
        "trace_step_index": 0,
        "llm_calls_made": 0
    }

    mock_res = MagicMock()
    mock_res.choices = [MagicMock(message=MagicMock(content='[]'))]

    with patch("litellm.completion", return_value=mock_res) as mock_completion:
        runner._plan_node(state)
        assert mock_completion.called
        kwargs = mock_completion.call_args[1]
        messages = kwargs["messages"]
        system_msg = next(msg["content"] for msg in messages if msg["role"] == "system")
        assert "Rule 12" in system_msg or "12. Do NOT invoke store actions" in system_msg or "Rule 13" in system_msg or "13. Do NOT invoke store actions" in system_msg


def test_goal_condition_nested_resolution():
    from react_agent_bridge.core.planner.goal import GoalCondition
    from react_agent_bridge.core.graph.state_graph import ApplicationStateGraph
    from react_agent_bridge.core.models import SerializedComponentEntry, RegistryDeltaMessage, SerializedStateSlot

    graph = ApplicationStateGraph()
    slot = SerializedStateSlot(key="projects", hookIndex=0)
    comp = SerializedComponentEntry(
        id="Store#1",
        displayName="Store",
        mountedAt=100,
        route="/",
        stateSlots=[slot]
    )
    graph.apply_delta(RegistryDeltaMessage(added=[comp], removed=[], updated=[]))
    
    projects_val = [
        {
            "id": "proj-1",
            "name": "Nebula Core",
            "tasks": [
                {"id": "t-1", "assignee": "Alice"},
                {"id": "t-2", "assignee": "Bob"}
            ]
        }
    ]
    graph.update_state_value("Store#1.projects", projects_val)

    # Test nested path resolution
    cond1 = GoalCondition(target="Store#1.projects[0].tasks[1].assignee", operator="equals", value="Bob")
    assert cond1.evaluate(graph) is True

    cond2 = GoalCondition(target="Store#1.projects[0].tasks[0].assignee", operator="equals", value="Alice")
    assert cond2.evaluate(graph) is True

    cond3 = GoalCondition(target="Store#1.projects[0].tasks[1].assignee", operator="equals", value="Charlie")
    assert cond3.evaluate(graph) is False


def test_goal_condition_virtual_slots():
    from react_agent_bridge.core.planner.goal import GoalCondition
    from react_agent_bridge.core.graph.state_graph import ApplicationStateGraph
    from react_agent_bridge.core.models import SerializedComponentEntry, RegistryDeltaMessage

    graph = ApplicationStateGraph()
    comp = SerializedComponentEntry(
        id="ProjectDetailView#r13",
        displayName="ProjectDetailView",
        mountedAt=100,
        route="/project/proj-123",
        stateSlots=[]
    )
    graph.apply_delta(RegistryDeltaMessage(added=[comp], removed=[], updated=[]))

    # isMounted virtual slot
    cond_mounted = GoalCondition(target="ProjectDetailView#r13.isMounted", operator="equals", value=True)
    assert cond_mounted.evaluate(graph) is True

    cond_unmounted = GoalCondition(target="LoginView#r5.isMounted", operator="equals", value=False)
    assert cond_unmounted.evaluate(graph) is True

    # route virtual slot
    cond_route = GoalCondition(target="ProjectDetailView#r13.route", operator="equals", value="/project/proj-123")
    assert cond_route.evaluate(graph) is True

    cond_route_miss = GoalCondition(target="ProjectDetailView#r13.route", operator="equals", value="/dashboard")
    assert cond_route_miss.evaluate(graph) is False


@pytest.mark.asyncio
async def test_compile_goal_target_validation():
    from react_agent_bridge.core.llm import LiteLLMAdapter
    from unittest.mock import patch, MagicMock
    import json

    adapter = LiteLLMAdapter(model="mock-model")

    registry_snapshot = {
        "components": {
            "DashboardView#r9": {
                "displayName": "DashboardView",
                "stateSlots": {
                    "newProjectName": ""
                }
            }
        }
    }

    # Attempt 1: Output contains invalid/hallucinated target (ZustandStore#AuthStore.projects.tasks[0].assignee)
    # Output must fail validation and trigger retry feedback
    mock_res_invalid = MagicMock()
    mock_res_invalid.choices = [MagicMock(message=MagicMock(content=json.dumps({
        "description": "Fail",
        "success_conditions": [
            {"target": "ZustandStore#AuthStore.projects.tasks[0].assignee", "operator": "equals", "value": "Developer"}
        ]
    })))]

    # Attempt 2: Corrects to allowed/virtual slot target
    mock_res_valid = MagicMock()
    mock_res_valid.choices = [MagicMock(message=MagicMock(content=json.dumps({
        "description": "Success",
        "success_conditions": [
            {"target": "ProjectDetailView.isMounted", "operator": "equals", "value": True}
        ]
    })))]

    with patch("litellm.acompletion", side_effect=[mock_res_invalid, mock_res_valid]) as mock_completion:
        goal = await adapter.compile_goal("Open board", registry_snapshot)
        assert mock_completion.call_count == 2
        assert goal.description == "Success"
        assert len(goal.success_conditions) == 1
        assert goal.success_conditions[0].target == "ProjectDetailView.isMounted"


def test_agent_runner_business_context_loading_and_parsing(tmp_path):
    from react_agent_bridge import ReactAgentBridge, AgentRunner

    context_file = tmp_path / "mock-context.md"
    context_file.write_text("""
## Component Glossary
### DashboardView
A dashboard view component.
routes matching `/dashboard`

## Workflow Definitions
### RegisterFlow
preconditions:
- AuthStore.isAuthenticated equals true
steps:
1. Click register
2. Enter details
success condition: AuthStore.isRegistered equals true
""", encoding="utf-8")

    bridge = ReactAgentBridge(host="localhost", port=8000)
    runner = AgentRunner(bridge, business_context=str(context_file))

    assert "GLOSSARY:" in runner.business_context
    assert "- DashboardView (Routes: /dashboard): A dashboard view component." in runner.business_context
    assert "WORKFLOWS:" in runner.business_context
    assert "- Workflow: RegisterFlow" in runner.business_context
    assert "Preconditions: AuthStore.isAuthenticated equals True" in runner.business_context
    assert "Steps:" in runner.business_context
    assert "* Click register" in runner.business_context
    assert "Success Condition: AuthStore.isRegistered equals True" in runner.business_context




