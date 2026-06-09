"""
Log capture layer for SSE streaming.

Intercepts rich.console.print() and loguru.logger output from agent modules
and pushes lines into an asyncio.Queue for real-time streaming to the browser.
"""

import asyncio
import sys
import threading
from io import StringIO
from contextlib import contextmanager
from typing import Generator

from loguru import logger
from rich.console import Console

# All modules whose module-level `console` we need to patch
_CONSOLE_MODULES = [
    "agents.polymarket_agent",
    "agents.kalshi_agent",
    "agents.niche_mapper",
    "agents.research_agent",
    "agents.chat_agent",
    "memory.learning_loop",
]


class LogCapture:
    """
    Captures rich console output and loguru logs into an asyncio.Queue.

    Usage:
        queue = asyncio.Queue()
        capture = LogCapture(queue, loop)
        with capture:
            orchestrator.run_polymarket_only()
        # queue now has all log lines
    """

    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop) -> None:
        self.queue = queue
        self.loop = loop
        self._original_consoles: dict[str, Console] = {}
        self._buffer = StringIO()
        self._capture_console = Console(
            file=self._buffer,
            force_terminal=True,
            width=120,
            no_color=False,
        )
        self._loguru_sink_id: int | None = None
        self._lock = threading.Lock()

    def _push(self, message: str) -> None:
        """Thread-safe push to the async queue."""
        lines = message.strip().splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped:
                try:
                    self.loop.call_soon_threadsafe(self.queue.put_nowait, stripped)
                except Exception:
                    pass

    def _flush_buffer(self) -> None:
        """Flush the StringIO buffer and push contents to the queue."""
        with self._lock:
            content = self._buffer.getvalue()
            if content:
                self._buffer.truncate(0)
                self._buffer.seek(0)
                self._push(content)

    def _patch_consoles(self) -> None:
        """Replace module-level console objects with our capturing console."""
        for mod_name in _CONSOLE_MODULES:
            mod = sys.modules.get(mod_name)
            if mod and hasattr(mod, "console"):
                self._original_consoles[mod_name] = mod.console
                mod.console = self._capture_console

    def _restore_consoles(self) -> None:
        """Restore original module-level console objects."""
        for mod_name, original in self._original_consoles.items():
            mod = sys.modules.get(mod_name)
            if mod:
                mod.console = original
        self._original_consoles.clear()

    def _loguru_sink(self, message) -> None:
        """Loguru sink that pushes to the queue."""
        self._flush_buffer()  # flush any pending rich output first
        text = str(message).strip()
        if text:
            self._push(text)

    def __enter__(self) -> "LogCapture":
        # Patch module-level consoles
        self._patch_consoles()

        # Add loguru sink
        self._loguru_sink_id = logger.add(
            self._loguru_sink,
            level="DEBUG",
            format="{time:HH:mm:ss} | {level} | {message}",
            colorize=False,
        )
        return self

    def __exit__(self, *args) -> None:
        # Flush any remaining buffer
        self._flush_buffer()

        # Remove loguru sink
        if self._loguru_sink_id is not None:
            try:
                logger.remove(self._loguru_sink_id)
            except ValueError:
                pass

        # Restore original consoles
        self._restore_consoles()

        # Signal end of stream
        try:
            self.loop.call_soon_threadsafe(self.queue.put_nowait, None)
        except Exception:
            pass


@contextmanager
def capture_logs(queue: asyncio.Queue, loop: asyncio.AbstractEventLoop) -> Generator[LogCapture, None, None]:
    """Convenience context manager for log capture."""
    cap = LogCapture(queue, loop)
    with cap:
        yield cap
