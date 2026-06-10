import os
import time
import json
import sqlite3
import pytest
import asyncio
import logging
from unittest.mock import MagicMock, patch

from react_agent_bridge.discovery.event import DiscoveryEvent, DiscoveryEventType
from react_agent_bridge.discovery.corpus import ObservationCorpus
from react_agent_bridge.discovery.recorder import HumanSessionRecorder
from react_agent_bridge.discovery.session import DiscoverySession
from react_agent_bridge.discovery.analyzer.slot_annotator import SlotAnnotationEngine
from react_agent_bridge.discovery.analyzer.workflow import WorkflowInferenceEngine
from react_agent_bridge.discovery.analyzer.precondition import PreconditionInferenceEngine
from react_agent_bridge.discovery.analyzer.constraint import ConstraintInferenceEngine
from react_agent_bridge.discovery.generator.context_writer import ContextWriter

@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_discovery_p3.db"
    return str(db_file)

@pytest.mark.asyncio
async def test_deterministic_version_hash(temp_db):
    corpus = ObservationCorpus(temp_db)
    
    mock_comp1 = MagicMock()
    mock_comp1.display_name = "ButtonPanel"
    mock_comp2 = MagicMock()
    mock_comp2.display_name = "Header"
    
    mock_bridge = MagicMock()
    mock_bridge.graph = MagicMock()
    mock_bridge.graph.get_mounted_components.return_value = [mock_comp1, mock_comp2]
    
    recorder1 = HumanSessionRecorder(mock_bridge, corpus, session_type="human")
    await recorder1.start()
    hash1 = recorder1.app_version_hash
    await recorder1.stop()
    
    recorder2 = HumanSessionRecorder(mock_bridge, corpus, session_type="human")
    await recorder2.start()
    hash2 = recorder2.app_version_hash
    await recorder2.stop()
    
    # Hash should be deterministic and identical for same component set
    assert hash1 == hash2
    assert hash1 != "initial_v1"

@pytest.mark.asyncio
async def test_version_hash_change_warning_and_weighting(temp_db, caplog):
    corpus = ObservationCorpus(temp_db)
    
    mock_bridge = MagicMock()
    mock_bridge.graph = MagicMock()
    mock_bridge.graph.get_slot_value.return_value = None
    
    # Session 1: Version A
    mock_comp1 = MagicMock()
    mock_comp1.display_name = "ComponentA"
    mock_bridge.graph.get_mounted_components.return_value = [mock_comp1]
    
    recorder1 = HumanSessionRecorder(mock_bridge, corpus, session_type="human")
    await recorder1.start()
    hashA = recorder1.app_version_hash
    
    # Record some slot changes in Session 1
    await recorder1.on_message({
        "type": "stateSnapshot",
        "target": "App.slot",
        "value": True
    })
    await recorder1.stop()
    
    # Session 2: Version B (Changed components)
    mock_comp2 = MagicMock()
    mock_comp2.display_name = "ComponentB"
    mock_bridge.graph.get_mounted_components.return_value = [mock_comp2]
    
    # Start second session to trigger version change warning
    with caplog.at_level(logging.WARNING):
        recorder2 = HumanSessionRecorder(mock_bridge, corpus, session_type="human")
        await recorder2.start()
        hashB = recorder2.app_version_hash
        
        # Record some slot changes in Session 2
        await recorder2.on_message({
            "type": "stateSnapshot",
            "target": "App.slot",
            "value": False
        })
        await recorder2.stop()
        
    assert hashA != hashB
    # Warning log should have been triggered
    assert any("version hash changed" in record.message.lower() for record in caplog.records)

@pytest.mark.asyncio
async def test_incremental_runs_history(temp_db):
    mock_bridge = MagicMock()
    mock_bridge.graph = MagicMock()
    mock_bridge._server = MagicMock()
    
    session = DiscoverySession(
        bridge=mock_bridge,
        output_path="./agent-context.md",
        db_path=temp_db,
        min_sessions=1
    )
    
    # Run generate() once
    res1 = await session.generate()
    last_run1 = await session.corpus.get_last_inference_run()
    assert last_run1 is not None
    ts1 = last_run1["timestamp"]
    
    # Run generate() again
    # We should have a second run recorded with a newer timestamp
    await asyncio.sleep(0.01)
    res2 = await session.generate()
    last_run2 = await session.corpus.get_last_inference_run()
    assert last_run2 is not None
    ts2 = last_run2["timestamp"]
    
    assert ts2 > ts1

@pytest.mark.asyncio
async def test_background_scheduler_loop(temp_db):
    mock_bridge = MagicMock()
    mock_bridge.graph = MagicMock()
    mock_bridge._server = MagicMock()
    
    # Use very small inference interval for testing loop
    session = DiscoverySession(
        bridge=mock_bridge,
        output_path="./agent-context.md",
        db_path=temp_db,
        inference_interval_hours=0.0001 # approx 0.36 seconds
    )
    
    # Start background scheduler
    session._start_bg_scheduler()
    assert session._bg_task is not None
    
    # Wait for loop to execute generate() at least once
    await asyncio.sleep(0.5)
    
    # Stop background scheduler
    session._stop_bg_scheduler()
    assert session._bg_task is None
    
    last_run = await session.corpus.get_last_inference_run()
    assert last_run is not None
