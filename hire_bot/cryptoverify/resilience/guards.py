from __future__ import annotations

import asyncio
import functools
import logging
import random
from typing import Any, Callable

from ..exceptions import ProviderBenched, ProviderCallFailed

logger = logging.getLogger("cryptoverify.resilience")


def with_timeout(func: Callable) -> Callable:
    @functools.wraps(func)
    async def wrapper(self, *args: Any, **kwargs: Any) -> Any:
        limit = float(getattr(self, "timeout_seconds", 8.0))
        try:
            return await asyncio.wait_for(func(self, *args, **kwargs), timeout=limit)
        except asyncio.TimeoutError:
            raise ProviderCallFailed(getattr(self, "name", "provider"), f"timed out after {limit:.0f}s", retryable=True)

    return wrapper


def with_retry(func: Callable) -> Callable:
    @functools.wraps(func)
    async def wrapper(self, *args: Any, **kwargs: Any) -> Any:
        attempts = max(1, int(getattr(self, "retry_attempts", 2)))
        last_error: ProviderCallFailed | None = None
        for attempt in range(attempts):
            try:
                return await func(self, *args, **kwargs)
            except ProviderCallFailed as error:
                last_error = error
                if not error.retryable or attempt == attempts - 1:
                    raise
                delay = (0.25 * (2**attempt)) + random.uniform(0, 0.2)
                logger.debug("retrying %s in %.2fs after %s", error.provider, delay, error.reason)
                await asyncio.sleep(delay)
        raise last_error if last_error else ProviderCallFailed(getattr(self, "name", "provider"), "unknown failure")

    return wrapper


def with_circuit_breaker(func: Callable) -> Callable:
    @functools.wraps(func)
    async def wrapper(self, *args: Any, **kwargs: Any) -> Any:
        breaker = getattr(self, "breaker", None)
        name = getattr(self, "name", "provider")
        if breaker is not None and not breaker.allows_call():
            raise ProviderBenched(name, breaker.seconds_until_retry())
        try:
            outcome = await func(self, *args, **kwargs)
        except ProviderCallFailed:
            if breaker is not None:
                breaker.record_failure()
            raise
        if breaker is not None:
            breaker.record_success()
        return outcome

    return wrapper


def shielded(func: Callable) -> Callable:
    return with_circuit_breaker(with_retry(with_timeout(func)))
