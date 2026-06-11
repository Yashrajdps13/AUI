import asyncio
import json
import logging
from typing import Dict, Set, Callable, Optional, Any

import websockets
from react_agent_bridge.core.dispatcher import CommandDispatcher
from react_agent_bridge.core.futures import CommandFutureManager
from react_agent_bridge.core.graph.state_graph import ApplicationStateGraph
from react_agent_bridge.core.exceptions import ConnectionLostError, CommandFailedError
from react_agent_bridge.core.models import parse_bridge_message
from react_agent_bridge.core.llm import BaseLLMAdapter, LiteLLMAdapter

logger = logging.getLogger("react_agent_bridge.client")


class ReactAgentBridge(CommandDispatcher):
    """
    Main entry point for the react-agent-bridge Python SDK runtime.
    Runs a WebSocket server to link with the browser-based React client.
    """
    def __init__(
        self,
        host: str = "localhost",
        port: int = 8000,
        business_logic: Optional[str] = None,
        llm_adapter: Optional[BaseLLMAdapter] = None
    ):
        super().__init__()
        self.host = host
        self.port = port
        self.business_logic_path = business_logic
        self.connection = None
        self._server = None
        self._discovery_recorder = None

        from react_agent_bridge.core.rules.registry import RuleRegistry
        from react_agent_bridge.core.rules.engine import RulesEngine

        # Core components
        self.futures_manager = CommandFutureManager()
        self.graph = ApplicationStateGraph()
        self.rules_engine = RulesEngine(RuleRegistry())
        self.llm_adapter = llm_adapter or LiteLLMAdapter()

        # Event Listeners
        self.listeners: Dict[str, Set[Callable]] = {
            "connect": set(),
            "disconnect": set(),
            "registry_update": set(),
            "log": set(),
            "state_update": set(),
        }

    def add_listener(self, event: str, callback: Callable):
        """Registers a callback for client events ('connect', 'disconnect', 'registry_update', 'log')."""
        if event in self.listeners:
            self.listeners[event].add(callback)

    def remove_listener(self, event: str, callback: Callable):
        """Unregisters a callback."""
        if event in self.listeners:
            self.listeners[event].discard(callback)

    def _trigger_event(self, event: str, *args, **kwargs):
        """Fires registered listener callbacks safely."""
        for callback in list(self.listeners.get(event, [])):
            try:
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback(*args, **kwargs))
                else:
                    callback(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in {event} listener callback: {e}")

    async def start(self):
        """Starts the WebSocket server and binds to the configured host and port."""
        self._server = await websockets.serve(self._handle_connection, self.host, self.port)
        logger.info(f"ReactAgentBridge WebSocket Server running at ws://{self.host}:{self.port}")

    async def stop(self):
        """Closes any active connection and terminates the WebSocket server cleanly."""
        if self.connection:
            await self.connection.close()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("ReactAgentBridge server stopped.")

    async def set_agent_status(self, status: str):
        """Sends an agentStatus command to the React client."""
        if self.connection:
            try:
                await self._send({"type": "agentStatus", "status": status})
            except Exception as e:
                logger.error(f"Failed to send agent status: {e}")

    async def wait_for_client(self):
        """Blocks asynchronously until a browser client connects to the bridge."""
        while not self.connection:
            await asyncio.sleep(0.1)

    async def _send(self, message: dict):
        """Serializes and sends a dictionary payload over the active socket connection."""
        if not self.connection:
            raise ConnectionLostError("Cannot send message: React bridge client is not connected.")
        await self.connection.send(json.dumps(message))

    async def _handle_connection(self, websocket):
        """Handles the lifecycle of a single incoming React client connection."""
        if self.connection:
            logger.warning("Replacing existing bridge connection with new client connection.")
            old_conn = self.connection
            self.connection = websocket
            try:
                await old_conn.close(code=4001, reason="Superceded by new connection.")
            except Exception:
                pass

        self.connection = websocket
        logger.info("React client connected successfully.")
        self._trigger_event("connect")

        # Request initial registry snapshot to sync state
        try:
            await self._send({"type": "getRegistry", "commandId": "initial-sync"})
        except Exception as e:
            logger.error(f"Failed to send initial registry sync request: {e}")
            if self.connection is websocket:
                self.connection = None
                self._trigger_event("disconnect")
            return

        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self._route_message(data)
                except Exception as e:
                    logger.error(f"Error handling message: {e}", exc_info=True)
        except websockets.exceptions.ConnectionClosedOK:
            logger.info("React client closed connection cleanly.")
        except Exception as e:
            logger.error(f"React client connection dropped with error: {e}")
        finally:
            if self.connection is websocket:
                self.connection = None
                self.futures_manager.reject_all("WebSocket connection closed")
                self.graph.clear()
                self._trigger_event("disconnect")

    async def _route_message(self, data: dict):
        """Routes and parses incoming bridge messages, updating graph and futures."""
        if getattr(self, "_discovery_recorder", None):
            await self._discovery_recorder.on_message(data)
        try:
            msg = parse_bridge_message(data)
        except Exception as e:
            logger.error(f"Protocol violation: Received malformed message: {data}. Error: {e}")
            return

        msg_type = msg.type

        if msg_type == "registryDelta":
            self.graph.apply_delta(msg)
            for comp in msg.added:
                asyncio.create_task(self._safe_subscribe(comp.id))
            self._trigger_event("registry_update", msg)

        elif msg_type == "stateSnapshot":
            self.graph.update_state_value(msg.target, msg.value)
            self._trigger_event("state_update", msg.target, msg.value)

        elif msg_type == "commandAck":
            if not msg.success:
                self.futures_manager.reject_future(
                    msg.commandId,
                    CommandFailedError(msg.error or "Command failed on bridge", msg_type)
                )
            else:
                self.futures_manager.resolve_future(msg.commandId, {"success": True})

        elif msg_type == "appLog":
            # Stream logs via console output or event listeners
            logger.info(f"[{msg.entry.source.upper()}] {msg.entry.message}")
            self._trigger_event("log", msg.entry)

        elif msg_type == "ledgerSnapshot":
            ledger_data = [item.model_dump() for item in msg.ledger]
            self.futures_manager.resolve_future(msg.commandId, {"success": True, "ledger": ledger_data})

        elif msg_type == "auditLogSnapshot":
            audit_data = [item.model_dump() for item in msg.auditLog]
            self.futures_manager.resolve_future(msg.commandId, {"success": True, "auditLog": audit_data})

        elif msg_type == "renderSettled":
            logger.debug(f"React commit rendering settled for target: {msg.target}")

        elif msg_type == "interaction":
            logger.debug(f"React client interaction: {msg.event} on {msg.componentId} ({msg.selector})")

        else:
            logger.warning(f"Unhandled message type: {msg_type}")

    async def _safe_subscribe(self, comp_id: str):
        if comp_id in self.graph.components:
            try:
                await self.subscribe(comp_id)
            except Exception as e:
                logger.debug(f"Subscription failed for component {comp_id}: {e}")

    def discover(
        self,
        output_path: str = "./agent-context.md",
        db_path: str = "./discovery.db",
        min_sessions: int = 3,
        inference_interval_hours: float = 24.0,
        min_confidence_for_workflow: float = 0.6,
        min_confidence_for_constraint: float = 0.7,
        golden_trace_min_confidence: float = 0.8
    ):
        """
        Starts Discovery Mode, returns a DiscoverySession.
        """
        from react_agent_bridge.discovery.session import DiscoverySession
        session = DiscoverySession(
            bridge=self,
            output_path=output_path,
            db_path=db_path,
            min_sessions=min_sessions,
            inference_interval_hours=inference_interval_hours,
            min_confidence_for_workflow=min_confidence_for_workflow,
            min_confidence_for_constraint=min_confidence_for_constraint,
            golden_trace_min_confidence=golden_trace_min_confidence
        )
        self._discovery_recorder = session.recorder
        return session

