import os
import asyncio
import logging
from typing import Optional, Callable

logger = logging.getLogger("react_agent_bridge.business_logic.loader")


class BusinessLogicLoader:
    """
    Loads raw markdown content from string or file path, and handles watch-to-reload triggers.
    """
    def __init__(self, path_or_str: str, on_reload: Optional[Callable[[str], None]] = None):
        self.path_or_str = path_or_str
        self.on_reload = on_reload
        
        # Check if it looks like a valid file path
        self.is_file = False
        if isinstance(path_or_str, str) and len(path_or_str) < 512:
            try:
                self.is_file = os.path.exists(path_or_str)
            except Exception:
                self.is_file = False
                
        self._watcher_task = None

    def load(self) -> str:
        """Loads and returns the raw string content."""
        if self.is_file:
            with open(self.path_or_str, "r", encoding="utf-8") as f:
                return f.read()
        return self.path_or_str

    def start_watching(self):
        """Starts watching the file in a background asyncio loop task."""
        if not self.is_file or not self.on_reload:
            return
        
        loop = asyncio.get_running_loop()
        self._watcher_task = loop.create_task(self._watch_loop())
        logger.info(f"Started file watcher for {self.path_or_str}")

    async def _watch_loop(self):
        try:
            # Attempt to use watchfiles
            from watchfiles import awatch
            async for changes in awatch(self.path_or_str):
                logger.info(f"File change detected for {self.path_or_str}, reloading...")
                content = self.load()
                await self._trigger_reload(content)
        except ImportError:
            # Fall back to polling modification times
            logger.debug("watchfiles package not installed. Falling back to file polling watcher.")
            try:
                last_mtime = os.path.getmtime(self.path_or_str)
            except Exception:
                last_mtime = 0.0

            while True:
                await asyncio.sleep(2.0)
                try:
                    current_mtime = os.path.getmtime(self.path_or_str)
                    if current_mtime != last_mtime:
                        last_mtime = current_mtime
                        logger.info(f"File change detected (polled) for {self.path_or_str}, reloading...")
                        content = self.load()
                        await self._trigger_reload(content)
                except Exception as e:
                    logger.debug(f"File poll checking failed: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in file watcher loop: {e}", exc_info=True)

    async def _trigger_reload(self, content: str):
        if self.on_reload:
            try:
                if asyncio.iscoroutinefunction(self.on_reload):
                    await self.on_reload(content)
                else:
                    self.on_reload(content)
            except Exception as e:
                logger.error(f"Error executing reload callback: {e}", exc_info=True)

    def stop_watching(self):
        """Cancels the active file watcher task."""
        if self._watcher_task:
            self._watcher_task.cancel()
            self._watcher_task = None
            logger.info(f"Stopped file watcher for {self.path_or_str}")
