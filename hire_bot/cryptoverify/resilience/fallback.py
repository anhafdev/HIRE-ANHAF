from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Sequence

from ..exceptions import NoProviderAnswered, ProviderCallFailed, ProvidersDisagree
from ..models import ProviderError

logger = logging.getLogger("cryptoverify.fallback")


def rotate(items: Sequence[Any], offset: int) -> list[Any]:
    if not items:
        return []
    position = offset % len(items)
    return list(items[position:]) + list(items[:position])


def usable_only(providers: Sequence[Any]) -> list[Any]:
    ready: list[Any] = []
    for provider in providers:
        if provider.is_usable():
            ready.append(provider)
        else:
            logger.debug("skipping %s: no credentials configured", provider.name)
    return ready


async def ask_until_one_answers(
    providers: Sequence[Any],
    action: Callable[[Any], Awaitable[Any]],
) -> tuple[Any, Any, list[ProviderError]]:
    failures: list[ProviderError] = []
    for provider in providers:
        try:
            outcome = await action(provider)
        except ProviderCallFailed as error:
            failures.append(ProviderError(provider=provider.name, reason=error.reason))
            logger.debug("provider %s failed: %s", provider.name, error.reason)
            continue
        except Exception as error:
            failures.append(ProviderError(provider=provider.name, reason=f"unexpected {type(error).__name__}: {error}"))
            logger.warning("provider %s raised unexpectedly", provider.name, exc_info=True)
            continue
        return outcome, provider, failures
    raise NoProviderAnswered(failures)


async def ask_two_and_compare(
    providers: Sequence[Any],
    action: Callable[[Any], Awaitable[Any]],
    fingerprint: Callable[[Any], Any],
) -> tuple[Any, Any, list[ProviderError]]:
    first, first_provider, failures = await ask_until_one_answers(providers, action)
    remaining = [item for item in providers if item is not first_provider]
    if not remaining:
        return first, first_provider, failures
    try:
        second, second_provider, more_failures = await ask_until_one_answers(remaining, action)
    except NoProviderAnswered as error:
        failures.extend(error.failures)
        return first, first_provider, failures
    failures.extend(more_failures)
    if fingerprint(first) != fingerprint(second):
        raise ProvidersDisagree(
            f"{first_provider.name} and {second_provider.name} report different money movements for the same txid"
        )
    return first, first_provider, failures


async def collect_health(providers: Sequence[Any]) -> dict[str, str]:
    async def probe(provider: Any) -> tuple[str, str]:
        if not provider.is_usable():
            return provider.name, "skipped_no_key"
        if provider.breaker is not None and not provider.breaker.allows_call():
            return provider.name, "benched"
        try:
            await provider.load_tip_height()
        except Exception as error:
            return provider.name, f"down ({type(error).__name__})"
        return provider.name, "up"

    pairs = await asyncio.gather(*(probe(item) for item in providers), return_exceptions=False)
    return dict(pairs)
