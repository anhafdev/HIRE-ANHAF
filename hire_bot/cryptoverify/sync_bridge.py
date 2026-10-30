from __future__ import annotations

import asyncio
import threading
from typing import Any, Awaitable


class BackgroundLoop:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def _ensure_running(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None or self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(target=self._loop.run_forever, name="cryptoverify-loop", daemon=True)
                self._thread.start()
            return self._loop

    def run(self, work: Awaitable[Any]) -> Any:
        loop = self._ensure_running()
        return asyncio.run_coroutine_threadsafe(work, loop).result()

    def shutdown(self) -> None:
        with self._lock:
            if self._loop is not None and not self._loop.is_closed():
                self._loop.call_soon_threadsafe(self._loop.stop)
                if self._thread is not None:
                    self._thread.join(timeout=5)
                self._loop.close()
            self._loop = None
            self._thread = None
