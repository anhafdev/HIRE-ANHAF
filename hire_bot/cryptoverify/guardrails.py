from __future__ import annotations

from decimal import Decimal

from .assessment import build_result, read_amount
from .codes import Code
from .config import Config
from .models import Network, VerifyResult, VerifyStatus
from .networks.txid_rules import inspect_txid


def inspect_request(
    config: Config,
    txid: str,
    network: Network,
    expected_amount: Decimal,
    invoice_id: str,
) -> tuple[tuple[str, Decimal] | None, VerifyResult | None]:
    amount = read_amount(expected_amount)
    if amount is None:
        return None, build_result(
            VerifyStatus.INVALID_INPUT,
            Code.MALFORMED_AMOUNT,
            "The expected amount is missing or not a positive number.",
            network=network,
            invoice_id=invoice_id or "",
        )

    if not invoice_id:
        return None, build_result(
            VerifyStatus.INVALID_INPUT,
            Code.MISSING_INVOICE_ID,
            "An invoice id is required so the same payment cannot be used twice.",
            network=network,
        )

    if not config.is_enabled(network):
        return None, build_result(
            VerifyStatus.INVALID_INPUT,
            Code.NETWORK_NOT_CONFIGURED,
            f"No deposit address is configured for {network.value}.",
            network=network,
            invoice_id=invoice_id,
        )

    clean_txid, other_chain = inspect_txid(txid, network)
    if clean_txid is None:
        if other_chain is not None:
            return None, build_result(
                VerifyStatus.WRONG_NETWORK,
                Code.TXID_BELONGS_TO_ANOTHER_CHAIN,
                f"That transaction hash belongs to {other_chain.value}, not {network.value}.",
                network=network,
                invoice_id=invoice_id,
                txid=str(txid or ""),
            )
        return None, build_result(
            VerifyStatus.INVALID_INPUT,
            Code.MALFORMED_TXID,
            "That does not look like a valid transaction hash.",
            network=network,
            invoice_id=invoice_id,
            txid=str(txid or ""),
        )

    return (clean_txid, amount), None


def already_used_result(network: Network, txid: str, invoice_id: str, owner: str, amount: Decimal) -> VerifyResult:
    return build_result(
        VerifyStatus.REUSED,
        Code.TXID_ALREADY_USED,
        "This transaction hash has already been used for another order. Please send a new payment.",
        network=network,
        invoice_id=invoice_id,
        txid=txid,
        expected_amount=amount,
        claimed_by_invoice=owner,
    )


def internal_error_result(network: Network, txid: str, invoice_id: str) -> VerifyResult:
    return build_result(
        VerifyStatus.PROVIDER_UNAVAILABLE,
        Code.INTERNAL_LOOKUP_ERROR,
        "We could not check this payment right now. Please try again in a minute.",
        network=network,
        invoice_id=str(invoice_id or ""),
        txid=str(txid or ""),
    )
