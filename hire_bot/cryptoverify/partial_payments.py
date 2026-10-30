from __future__ import annotations

from decimal import Decimal
from typing import Any

from .amounts import smallest_acceptable_amount
from .assessment import build_result
from .codes import Code
from .models import VerifyResult, VerifyStatus
from .pricing import trim_zeros, usd_value


async def refresh_totals(session: Any) -> None:
    request = session.request
    if request is None:
        return
    stored = await session.verifier.storage.recall_invoice_payments(session.invoice_id, request.network.value)
    session.payments = [(txid, trim_zeros(Decimal(amount))) for txid, amount in stored]
    session.amount_paid_total = trim_zeros(sum((amount for _, amount in session.payments), Decimal(0)))
    session.amount_remaining = trim_zeros(max(Decimal(0), request.amount - session.amount_paid_total))


def remaining_note(session: Any) -> str:
    request = session.request
    note = (
        f"Received {session.amount_paid_total} of {request.amount} {request.unit} so far. "
        f"Remaining: {session.amount_remaining} {request.unit}"
    )
    if session.quote is not None:
        note += f" (about ${usd_value(session.amount_remaining, session.quote)})"
    return note + "."


def settled_result(session: Any, latest: VerifyResult) -> VerifyResult:
    request = session.request
    total = session.amount_paid_total
    return build_result(
        VerifyStatus.CONFIRMED,
        Code.PAYMENT_FINAL,
        f"Invoice settled: received {total} {request.unit} across {len(session.payments)} payment(s). Thank you.",
        network=request.network,
        invoice_id=request.invoice_id,
        txid=latest.txid,
        amount=total,
        expected_amount=request.amount,
        surplus=max(Decimal(0), total - request.amount),
        confirmations=latest.confirmations,
        required_confirmations=latest.required_confirmations,
        block_height=latest.block_height,
        block_time=latest.block_time,
        provider_used=latest.provider_used,
    )


def still_short_result(session: Any, latest: VerifyResult) -> VerifyResult:
    request = session.request
    return build_result(
        VerifyStatus.UNDERPAID,
        Code.AMOUNT_BELOW_EXPECTED,
        remaining_note(session),
        network=request.network,
        invoice_id=request.invoice_id,
        txid=latest.txid,
        amount=session.amount_paid_total,
        expected_amount=request.amount,
        confirmations=latest.confirmations,
        required_confirmations=latest.required_confirmations,
        provider_used=latest.provider_used,
    )


async def settle_after_check(session: Any, txid: str, result: VerifyResult, on_update: Any, live: bool) -> VerifyResult:
    request = session.request
    storage = session.verifier.storage
    counted = {paid_txid for paid_txid, _ in session.payments}
    if (
        result.status is VerifyStatus.UNDERPAID
        and result.amount is not None
        and result.amount > 0
        and result.txid not in counted
    ):
        result = await session.reverify_for_amount(txid, result.amount, on_update, live)
    if result.status is VerifyStatus.CONFIRMED and result.amount is not None and result.amount > 0:
        await storage.remember_invoice_payment(
            session.invoice_id, request.network.value, result.txid or txid, str(trim_zeros(result.amount))
        )
    await refresh_totals(session)
    floor = smallest_acceptable_amount(request.amount, session.config, request.network)
    if session.amount_paid_total >= floor:
        return settled_result(session, result)
    if result.status is VerifyStatus.CONFIRMED or result.status is VerifyStatus.UNDERPAID:
        return still_short_result(session, result)
    return result
