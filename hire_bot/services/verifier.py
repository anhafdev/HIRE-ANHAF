import logging
from decimal import Decimal

from cryptoverify import (
    CheckoutSession,
    DepositVerifier,
    Network,
    Tier,
    VerifyResult,
    VerifyStatus,
    build_receipt,
)
from cryptoverify.codes import advice_for
from cryptoverify.receipt import save_receipt_files

from config import CHECKOUT_EXPIRY_MINUTES, CV_CONFIG

logger = logging.getLogger(__name__)

_verifier: DepositVerifier | None = None


def get_verifier() -> DepositVerifier:
    global _verifier
    if _verifier is None:
        _verifier = DepositVerifier(CV_CONFIG)
    return _verifier


async def close():
    global _verifier
    if _verifier is not None:
        await _verifier.close()
    _verifier = None


def new_session(invoice_id: str | None = None) -> CheckoutSession:
    return CheckoutSession(get_verifier(), invoice_id=invoice_id, expiry_minutes=CHECKOUT_EXPIRY_MINUTES)


async def watch_existing(
    txid: str, network: Network, amount: Decimal, invoice_id: str, invoice_created_at, stop_after_seconds: float, on_update=None,
) -> VerifyResult:
    return await get_verifier().watch(
        txid=txid,
        network=network,
        expected_amount=amount,
        invoice_id=invoice_id,
        invoice_created_at=invoice_created_at,
        on_update=on_update,
        stop_after_seconds=max(1.0, stop_after_seconds),
        settle_at=Tier.CONFIRMED,
    )


def demo_result(network: Network, amount: Decimal, invoice_id: str, txid: str) -> VerifyResult:
    return VerifyResult(
        status=VerifyStatus.CONFIRMED,
        code="demo_mode",
        message="Demo mode — verification skipped.",
        network=network,
        txid=txid,
        invoice_id=invoice_id,
        amount=amount,
        expected_amount=amount,
        confirmations=1,
        required_confirmations=1,
        provider_used="demo",
    )


def error_result(network: Network, invoice_id: str, txid: str) -> VerifyResult:
    return VerifyResult(
        status=VerifyStatus.PROVIDER_UNAVAILABLE,
        code="internal_error",
        message="Something went wrong while verifying this payment. It will be checked manually.",
        network=network,
        txid=txid,
        invoice_id=invoice_id,
    )


def admin_reason(result: VerifyResult) -> str:
    return f"{result.message} ({advice_for(result.code)})"


def build_and_save_receipt(session, result: VerifyResult):
    try:
        receipt = build_receipt(session, result)
        if CV_CONFIG.receipt_dir:
            save_receipt_files(receipt, CV_CONFIG.receipt_dir)
        return receipt
    except Exception:
        logger.exception("could not build receipt for invoice %s", session.invoice_id)
        return None
