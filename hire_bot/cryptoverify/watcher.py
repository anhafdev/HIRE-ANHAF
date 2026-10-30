from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Awaitable, Callable

from .models import Network, Tier, VerifyResult, VerifyStatus

logger = logging.getLogger("cryptoverify.watcher")

GIVE_UP_STATUSES = {
    VerifyStatus.CONFIRMED,
    VerifyStatus.UNDERPAID,
    VerifyStatus.REUSED,
    VerifyStatus.STALE,
    VerifyStatus.WRONG_ADDRESS,
    VerifyStatus.WRONG_TOKEN,
    VerifyStatus.WRONG_NETWORK,
    VerifyStatus.FAILED_TX,
    VerifyStatus.INVALID_INPUT,
}


def next_pause(seconds_elapsed: float) -> float:
    if seconds_elapsed < 30:
        return 1.0
    if seconds_elapsed < 120:
        return 5.0
    return 15.0


async def follow_until_final(
    verifier: Any,
    txid: str,
    network: Network,
    expected_amount: Decimal,
    invoice_id: str,
    invoice_created_at: datetime | None = None,
    on_update: Callable[[VerifyResult], Awaitable[None] | None] | None = None,
    stop_after_seconds: float = 1800.0,
    settle_at: Tier = Tier.CONFIRMED,
) -> VerifyResult:
    started = asyncio.get_running_loop().time()
    last_signature: tuple | None = None
    latest: VerifyResult | None = None

    while True:
        latest = await verifier.verify(
            txid=txid,
            network=network,
            expected_amount=expected_amount,
            invoice_id=invoice_id,
            invoice_created_at=invoice_created_at,
        )
        signature = (latest.status, latest.confirmations)
        if signature != last_signature:
            last_signature = signature
            if on_update is not None:
                outcome = on_update(latest)
                if asyncio.iscoroutine(outcome):
                    await outcome
        if latest.status in GIVE_UP_STATUSES or latest.is_acceptable(settle_at):
            return latest
        elapsed = asyncio.get_running_loop().time() - started
        if elapsed >= stop_after_seconds:
            return latest
        await asyncio.sleep(next_pause(elapsed))
