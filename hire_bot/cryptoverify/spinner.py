from __future__ import annotations

import asyncio
import sys
import time
from typing import Any, Awaitable, Callable, TextIO

UNICODE_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
ASCII_FRAMES = ("|", "/", "-", "\\")
DEFAULT_INTERVAL = 0.08


def _is_tty(stream: TextIO) -> bool:
    try:
        return bool(stream.isatty())
    except Exception:
        return False


def _supports_unicode(stream: TextIO) -> bool:
    encoding = (getattr(stream, "encoding", None) or "").lower()
    if not encoding:
        return False
    try:
        UNICODE_FRAMES[0].encode(encoding)
        return True
    except Exception:
        return False


class Spinner:
    """A live, self-clearing terminal spinner for real-time waits (network calls, chain polling).

    Silently does nothing when the target stream is not an interactive terminal (piped output,
    log files, captured test output), so it never pollutes non-interactive output and never
    changes what a caller receives from the awaited work.
    """

    def __init__(self, stream: TextIO | None = None, interval: float = DEFAULT_INTERVAL) -> None:
        self._stream = stream or sys.stdout
        self._interval = interval
        self._enabled = _is_tty(self._stream)
        self._frames = UNICODE_FRAMES if _supports_unicode(self._stream) else ASCII_FRAMES
        self._task: asyncio.Task | None = None
        self._label = ""
        self._detail: Callable[[float], str] | None = None
        self._started_at: float | None = None
        self._width = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _elapsed(self) -> float:
        return time.monotonic() - self._started_at if self._started_at is not None else 0.0

    def _write(self, text: str) -> None:
        self._width = max(self._width, len(text))
        self._stream.write("\r" + text.ljust(self._width))
        self._stream.flush()

    async def _spin(self) -> None:
        index = 0
        try:
            while True:
                frame = self._frames[index % len(self._frames)]
                extra = f"  {self._detail(self._elapsed())}" if self._detail else ""
                self._write(f"{frame} {self._label}  [{self._elapsed():0.0f}s]{extra}")
                index += 1
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            pass

    def start(self, label: str, detail: Callable[[float], str] | None = None) -> None:
        self._label = label
        self._detail = detail
        if self._started_at is None:
            self._started_at = time.monotonic()
        if self._enabled and self._task is None:
            self._task = asyncio.create_task(self._spin())

    async def pause(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._enabled and self._width:
            self._stream.write("\r" + " " * self._width + "\r")
            self._stream.flush()

    async def stop(self) -> None:
        await self.pause()
        self._started_at = None
        self._width = 0


async def with_spinner(label: str, awaitable: Awaitable[Any]) -> Any:
    """Run one awaited call while showing a live spinner labelled `label`."""
    spinner = Spinner()
    spinner.start(label)
    try:
        return await awaitable
    finally:
        await spinner.stop()
