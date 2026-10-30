from __future__ import annotations

import time
from enum import Enum


class BreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, cooldown_seconds: float = 60.0) -> None:
        self.failure_threshold = max(1, failure_threshold)
        self.cooldown_seconds = max(1.0, cooldown_seconds)
        self._failures = 0
        self._opened_at = 0.0
        self._state = BreakerState.CLOSED

    @property
    def state(self) -> BreakerState:
        if self._state is BreakerState.OPEN and self.seconds_until_retry() <= 0:
            self._state = BreakerState.HALF_OPEN
        return self._state

    def seconds_until_retry(self) -> float:
        if self._state is not BreakerState.OPEN:
            return 0.0
        elapsed = time.monotonic() - self._opened_at
        return max(0.0, self.cooldown_seconds - elapsed)

    def allows_call(self) -> bool:
        return self.state is not BreakerState.OPEN

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = 0.0
        self._state = BreakerState.CLOSED

    def record_failure(self) -> None:
        if self._state is BreakerState.HALF_OPEN:
            self._trip()
            return
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._trip()

    def _trip(self) -> None:
        self._state = BreakerState.OPEN
        self._opened_at = time.monotonic()
        self._failures = self.failure_threshold

    def reset(self) -> None:
        self._failures = 0
        self._opened_at = 0.0
        self._state = BreakerState.CLOSED
