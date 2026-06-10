import asyncio
import logging
from typing import Any, List, Literal, Optional
from react_agent_bridge.core.exceptions import (
    CommandTimeoutError,
    CommandFailedError,
    RuleViolationError
)

logger = logging.getLogger("react_agent_bridge.dispatcher")


class CommandDispatcher:
    """
    Base class providing outbound command helper methods.
    Intended to be inherited by ReactAgentBridge.
    """
    def __init__(self):
        # Initialized by ReactAgentBridge
        self.futures_manager = None
        self.rules_engine = None
        self.graph = None

    async def _send(self, message: dict):
        """Must be implemented by the subclass."""
        raise NotImplementedError

    async def _send_command(self, cmd: dict, timeout: float = 5.0) -> dict:
        """
        Validates, registers a future, dispatches the command, and waits for settlement.
        """
        # 1. Rules Engine Pre-flight validation
        if self.rules_engine and self.graph:
            # Avoid circular import at startup
            from react_agent_bridge.core.rules.result import RuleResult
            
            result = self.rules_engine.evaluate(cmd, self.graph)
            if not result.valid:
                violation_msgs = [f"{v.rule_name}: {v.message}" for v in result.violations]
                logger.warning(f"Command pre-flight validation failed: {violation_msgs}")
                raise RuleViolationError(
                    f"Command validation failed: {violation_msgs[0]}",
                    violation_details={"violations": [v.__dict__ for v in result.violations]}
                )

        # 2. Register future
        cmd_id, fut = self.futures_manager.create_future()
        cmd["commandId"] = cmd_id

        # 3. Transmit command
        logger.debug(f"Sending command: {cmd}")
        await self._send(cmd)

        # 4. Wait for resolution/timeout
        try:
            res = await asyncio.wait_for(fut, timeout=timeout)
            return res
        except asyncio.TimeoutError:
            self.futures_manager.clear_future(cmd_id)
            logger.error(f"Command {cmd_id} ({cmd['type']}) timed out after {timeout} seconds.")
            raise CommandTimeoutError(f"Command timed out waiting for Ack: {cmd['type']}")
        except Exception as e:
            logger.error(f"Command {cmd_id} ({cmd['type']}) failed: {e}")
            raise

    async def set_state(self, target: str, value: Any, timeout: float = 5.0) -> bool:
        """Mutates a component state slot value."""
        cmd = {
            "type": "setState",
            "target": target,
            "value": value
        }
        res = await self._send_command(cmd, timeout=timeout)
        if not res.get("success", False):
            raise CommandFailedError(res.get("error", "setState failed"), "setState")
        return True

    async def dispatch_event(
        self,
        target: str,
        event: Literal["click", "change", "focus"],
        payload: Any = None,
        timeout: float = 5.0
    ) -> bool:
        """Dispatches an interactive event (click, change, focus) targeting a selector or component."""
        cmd = {
            "type": "dispatchEvent",
            "target": target,
            "event": event
        }
        if payload is not None:
            cmd["payload"] = payload
        res = await self._send_command(cmd, timeout=timeout)
        if not res.get("success", False):
            raise CommandFailedError(res.get("error", "dispatchEvent failed"), "dispatchEvent")
        return True

    async def call_action(self, target: str, args: List[Any], timeout: float = 5.0) -> bool:
        """Calls a store action slot with argument list."""
        cmd = {
            "type": "callAction",
            "target": target,
            "args": args
        }
        res = await self._send_command(cmd, timeout=timeout)
        if not res.get("success", False):
            raise CommandFailedError(res.get("error", "callAction failed"), "callAction")
        return True

    async def query_state(self, target: str, timeout: float = 5.0) -> Any:
        """Queries the current value of a state slot. The value is retrieved from the state graph."""
        cmd = {
            "type": "queryState",
            "target": target
        }
        # The bridge sends a stateSnapshot before the commandAck, which updates the graph
        await self._send_command(cmd, timeout=timeout)
        if self.graph:
            return self.graph.get_slot_value(target)
        return None

    async def get_registry(self, timeout: float = 5.0) -> bool:
        """Forces the bridge to synchronize its component registry and state slot descriptions."""
        cmd = {
            "type": "getRegistry"
        }
        res = await self._send_command(cmd, timeout=timeout)
        return res.get("success", False)

    async def subscribe(self, target: str, timeout: float = 5.0) -> bool:
        """Subscribes to live state committing updates for a target slot or component."""
        cmd = {
            "type": "subscribe",
            "target": target
        }
        res = await self._send_command(cmd, timeout=timeout)
        return res.get("success", False)

    async def unsubscribe(self, target: str, timeout: float = 5.0) -> bool:
        """Unsubscribes from live state committing updates for a target slot or component."""
        cmd = {
            "type": "unsubscribe",
            "target": target
        }
        res = await self._send_command(cmd, timeout=timeout)
        return res.get("success", False)

    async def query_ledger(self, timeout: float = 5.0) -> List[dict]:
        """Queries the browser console ledger snapshot (streamed logs)."""
        cmd = {
            "type": "queryLedger"
        }
        res = await self._send_command(cmd, timeout=timeout)
        # The future is resolved on ledgerSnapshot message carrying the ledger list
        return res.get("ledger", [])

    async def query_audit_log(self, timeout: float = 5.0) -> List[dict]:
        """Queries the append-only command audit log from the browser bridge."""
        cmd = {
            "type": "queryAuditLog"
        }
        res = await self._send_command(cmd, timeout=timeout)
        # The future is resolved on auditLogSnapshot message carrying the auditLog list
        return res.get("auditLog", [])

    async def wait_for(
        self,
        target: str,
        operator: Literal["equals", "truthy", "falsy", "changed", "contains", "includes"],
        value: Any = None,
        timeout_ms: int = 5000,
        timeout: float = 6.0
    ) -> bool:
        """Waits for a state slot condition to be met on the browser bridge."""
        condition = {"operator": operator}
        if value is not None:
            condition["value"] = value

        cmd = {
            "type": "waitFor",
            "target": target,
            "condition": condition,
            "timeoutMs": timeout_ms
        }
        res = await self._send_command(cmd, timeout=timeout)
        if not res.get("success", False):
            raise CommandFailedError(res.get("error", "waitFor condition failed/timed out"), "waitFor")
        return True
