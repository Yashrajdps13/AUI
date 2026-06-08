import asyncio
import uuid
import logging
from typing import Dict, Tuple
from react_agent_bridge.core.exceptions import ConnectionLostError

logger = logging.getLogger("react_agent_bridge.futures")


class CommandFutureManager:
    def __init__(self):
        self._pending: Dict[str, asyncio.Future] = {}

    def create_future(self) -> Tuple[str, asyncio.Future]:
        """Generates a UUID commandId, creates an asyncio.Future, and stores it in the pending map."""
        command_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending[command_id] = fut
        return command_id, fut

    def resolve_future(self, command_id: str, result: dict):
        """Resolves the future associated with command_id with the provided result."""
        fut = self._pending.pop(command_id, None)
        if fut and not fut.done():
            fut.set_result(result)
            logger.debug(f"Resolved future for command {command_id}")
        else:
            logger.debug(f"Attempted to resolve unknown or already done command {command_id}")

    def reject_future(self, command_id: str, exception: Exception):
        """Rejects the future associated with command_id with the provided exception."""
        fut = self._pending.pop(command_id, None)
        if fut and not fut.done():
            fut.set_exception(exception)
            logger.debug(f"Rejected future for command {command_id}")

    def reject_all(self, reason: str):
        """Rejects all pending futures with a ConnectionLostError. Called on WS disconnection."""
        logger.debug(f"Rejecting all pending futures: {reason}")
        for command_id, fut in list(self._pending.items()):
            if not fut.done():
                fut.set_exception(ConnectionLostError(reason))
        self._pending.clear()
        
    def clear_future(self, command_id: str):
        """Removes a future from the pending map without resolving or rejecting it. Useful on timeout."""
        self._pending.pop(command_id, None)
