from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from .amounts import (
    add_up,
    pick_transfers_for_contract,
    pick_transfers_to_address,
    read_amount,
    smallest_acceptable_amount,
    tx_below_invoice_height,
    tx_predates_invoice,
)
from .codes import Code
from .config import Config
from .models import TOKEN_CONTRACT_BY_NETWORK, ChainTransaction, Network, VerifyResult, VerifyStatus
from .pricing import PriceQuote, describe_shortfall


def build_result(status: VerifyStatus, code: str, message: str, **extras) -> VerifyResult:
    return VerifyResult(status=status, code=code, message=message, **extras)


def judge_payment(
    tx: ChainTransaction,
    config: Config,
    network: Network,
    expected_amount: Decimal,
    invoice_created_at: datetime | None,
    invoice_tip_height: int | None,
    locked_quote: PriceQuote | None = None,
) -> VerifyResult:
    our_address = config.address_for(network)
    expected_contract = TOKEN_CONTRACT_BY_NETWORK.get(network)
    required = config.min_confirmations_for(network)
    common = {
        "network": network,
        "txid": tx.txid,
        "expected_amount": expected_amount,
        "confirmations": tx.confirmations,
        "required_confirmations": required,
        "block_height": tx.block_height,
        "block_time": tx.block_time,
        "provider_used": tx.reported_by,
        "raw": tx.raw,
    }

    if not tx.found:
        return build_result(
            VerifyStatus.NOT_FOUND,
            Code.TX_NOT_ON_CHAIN_YET,
            "We cannot see this transaction on the network yet. Wait a moment and try again.",
            **common,
        )

    if not tx.succeeded:
        return build_result(
            VerifyStatus.FAILED_TX,
            Code.TX_REVERTED_ON_CHAIN,
            "This transaction failed on the blockchain, so no funds moved. Please send a new payment.",
            **common,
        )

    if not tx.settled_in_block and not tx.transfers:
        return build_result(
            VerifyStatus.NOT_FOUND,
            Code.TX_NOT_ON_CHAIN_YET,
            "The transaction is still propagating and its details are not readable yet. Try again shortly.",
            **common,
        )

    on_contract = pick_transfers_for_contract(tx.transfers, expected_contract)
    if expected_contract is not None and not on_contract:
        return build_result(
            VerifyStatus.WRONG_TOKEN,
            Code.UNEXPECTED_TOKEN_CONTRACT,
            "This transaction does not move the USDT token we accept on this network.",
            **common,
        )

    to_us = pick_transfers_to_address(on_contract, our_address)
    if not to_us:
        return build_result(
            VerifyStatus.WRONG_ADDRESS,
            Code.PAYS_A_DIFFERENT_ADDRESS,
            "This transaction does not pay our deposit address. Please check the address you sent to.",
            **common,
        )

    received = add_up(to_us)
    common["amount"] = received
    common["surplus"] = received - expected_amount if received > expected_amount else Decimal(0)

    if invoice_created_at is not None and tx_predates_invoice(tx, invoice_created_at, config.clock_skew_minutes):
        return build_result(
            VerifyStatus.STALE,
            Code.TX_OLDER_THAN_INVOICE,
            "This payment was made before the invoice existed, so it cannot be used for this order.",
            **common,
        )

    if tx_below_invoice_height(tx, invoice_tip_height, config.reorg_buffer_blocks):
        return build_result(
            VerifyStatus.STALE,
            Code.TX_BELOW_INVOICE_HEIGHT,
            "This payment was mined before the invoice was created, so it cannot be used for this order.",
            **common,
        )

    if received < smallest_acceptable_amount(expected_amount, config, network):
        return build_result(
            VerifyStatus.UNDERPAID,
            Code.AMOUNT_BELOW_EXPECTED,
            describe_shortfall(received, expected_amount, locked_quote),
            **common,
        )

    if not tx.settled_in_block:
        if tx.replaceable and config.reject_rbf_on_detected:
            return build_result(
                VerifyStatus.NOT_FOUND,
                Code.TX_REPLACEABLE_STILL_PENDING,
                "This payment is still replaceable in the mempool. We will accept it once it is mined.",
                rbf_risk=True,
                **common,
            )
        return build_result(
            VerifyStatus.DETECTED,
            Code.PAYMENT_SEEN_IN_MEMPOOL,
            "Payment spotted on the network and waiting to be mined. We can start already.",
            rbf_risk=tx.replaceable,
            **common,
        )

    if tx.confirmations < required:
        return build_result(
            VerifyStatus.DETECTED,
            Code.PAYMENT_SEEN_IN_MEMPOOL,
            f"Payment found with {tx.confirmations} of {required} confirmations. Almost final.",
            rbf_risk=tx.replaceable,
            **common,
        )

    return build_result(
        VerifyStatus.CONFIRMED,
        Code.PAYMENT_FINAL,
        f"Payment of {received} confirmed on chain. Thank you.",
        **common,
    )
