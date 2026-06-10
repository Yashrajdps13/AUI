import os
import time
import pytest
import sqlite3
from unittest.mock import MagicMock, patch

from react_agent_bridge import ReactAgentBridge, AgentRunner
from react_agent_bridge.core.graph.state_graph import ApplicationStateGraph
from react_agent_bridge.core.models import RegistryDeltaMessage, SerializedComponentEntry, SerializedStateSlot
from react_agent_bridge.core.planner.goal import Goal, GoalCondition
from react_agent_bridge.core.llm import BaseLLMAdapter, StructuredAction
from react_agent_bridge.discovery.traces import GoldenTraceStore, GoldenTrace, GoldenTraceStep


class SimpleMockLLMAdapter(BaseLLMAdapter):
    def __init__(self, action: StructuredAction, mock_goal: Goal):
        self.action = action
        self.mock_goal = mock_goal

    async def call(self, prompt: str, tools: list, goal: Goal) -> StructuredAction:
        return self.action

    async def compile_goal(self, query: str, registry_snapshot: dict) -> Goal:
        return self.mock_goal


@pytest.fixture
def temp_db(tmp_path):
    return str(tmp_path / "test_traces.db")


@pytest.mark.asyncio
async def test_golden_trace_recording_and_replay(temp_db):
    # Setup mock component/slots
    slot = SerializedStateSlot(key="powerLevel", hookIndex=0)
    comp = SerializedComponentEntry(id="Reactor", displayName="Reactor", mountedAt=100, route="/", stateSlots=[slot])
    
    # Mock bridge class
    class MockBridge(ReactAgentBridge):
        def __init__(self):
            super().__init__(host="localhost", port=8001)
            self.graph.apply_delta(RegistryDeltaMessage(added=[comp], removed=[], updated=[]))
            self.graph.update_state_value("Reactor.powerLevel", 10)
            self.connection = MagicMock()
            self.commands_sent = []

        async def set_state(self, target: str, value) -> bool:
            self.commands_sent.append(("setState", target, value))
            self.graph.update_state_value(target, value)
            return True

    bridge = MockBridge()
    bridge.connection = MagicMock()

    goal = Goal(
        description="Overdrive Reactor",
        success_conditions=[
            GoalCondition(target="Reactor.powerLevel", operator="equals", value=9000)
        ],
        max_steps=5
    )

    action = StructuredAction(name="set_state", arguments={"target": "Reactor.powerLevel", "value": 9000})
    adapter = SimpleMockLLMAdapter(action, goal)

    runner = AgentRunner(bridge, model="mock-model", db_path=temp_db)
    bridge.llm_adapter = adapter

    # Mock litellm completion to return the setState command
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = """```json
    [
        {"type": "setState", "target": "Reactor.powerLevel", "value": 9000}
    ]
    ```"""
    mock_response.choices = [mock_choice]

    with patch("litellm.completion", return_value=mock_response) as mock_complete:
        # 1. Run 1: Normal planning via Mock LLM Adapter
        res1 = await runner.execute("Set reactor power level to 9000")
        assert res1["status"] == "executed"
        assert mock_complete.call_count == 1
        
        # Assert trace was stored in SQLite
        store = GoldenTraceStore(temp_db)
        traces = store.find_applicable_traces("Overdrive Reactor", {"Reactor.powerLevel": 10}, min_confidence=0.8)
        assert len(traces) == 1
        trace = traces[0]
        assert trace.workflow_name == "Overdrive Reactor"
        assert len(trace.steps) == 1

        # Reset state to test replay
        bridge.graph.update_state_value("Reactor.powerLevel", 10)
        
        # Reset mock call counts
        mock_complete.reset_mock()
        
        # 2. Run 2: Trace Replay (should NOT call LLM adapter / litellm completion)
        res2 = await runner.execute("Set reactor power level to 9000")
        
        assert res2["status"] == "executed"
        # Verify zero LLM planner calls were made!
        assert res2.get("llm_calls_made", 0) == 0
        assert mock_complete.call_count == 0


@pytest.mark.asyncio
async def test_golden_trace_confidence_decay(temp_db):
    # Setup mock component/slots
    slot = SerializedStateSlot(key="mode", hookIndex=0)
    comp = SerializedComponentEntry(id="Device", displayName="Device", mountedAt=100, route="/", stateSlots=[slot])

    class MockBridge(ReactAgentBridge):
        def __init__(self):
            super().__init__(host="localhost", port=8002)
            self.graph.apply_delta(RegistryDeltaMessage(added=[comp], removed=[], updated=[]))
            self.graph.update_state_value("Device.mode", "idle")
            self.connection = MagicMock()
            self.commands_sent = []
            self.fail_mode = False

        async def set_state(self, target: str, value) -> bool:
            self.commands_sent.append(("setState", target, value))
            if not self.fail_mode:
                self.graph.update_state_value(target, value)
            return True

    bridge = MockBridge()
    bridge.connection = MagicMock()

    goal = Goal(
        description="Boost Device",
        success_conditions=[
            GoalCondition(target="Device.mode", operator="equals", value="boost")
        ]
    )

    action = StructuredAction(name="set_state", arguments={"target": "Device.mode", "value": "boost"})
    adapter = SimpleMockLLMAdapter(action, goal)

    runner = AgentRunner(bridge, model="mock-model", db_path=temp_db)
    bridge.llm_adapter = adapter

    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = """```json
    [
        {"type": "setState", "target": "Device.mode", "value": "boost"}
    ]
    ```"""
    mock_response.choices = [mock_choice]

    with patch("litellm.completion", return_value=mock_response) as mock_complete:
        # 1. Run successfully to record trace
        await runner.execute("Set mode to boost")
        
        store = GoldenTraceStore(temp_db)
        traces = store.find_applicable_traces("Boost Device", {"Device.mode": "idle"}, min_confidence=0.8)
        assert len(traces) == 1
        trace_id = traces[0].trace_id
        assert traces[0].confidence == 1.0

        # 2. Reset state & make execution fail (simulate broken trace replay due to changed UI behavior)
        bridge.graph.update_state_value("Device.mode", "idle")
        bridge.fail_mode = True  # Mode won't update, causing post-condition check fail
        
        mock_complete.reset_mock()
        res = await runner.execute("Set mode to boost")
        
        # Verify trace confidence decayed in store
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT confidence FROM golden_traces WHERE trace_id = ?", (trace_id,))
        row = cursor.fetchone()
        conn.close()
        
        # Confidence decayed from 1.0 to 0.7
        assert row is not None
        assert row[0] == pytest.approx(0.7)
