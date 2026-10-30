from __future__ import annotations


class Code:
    PAYMENT_FINAL = "payment_final"
    PAYMENT_SEEN_IN_MEMPOOL = "payment_seen_in_mempool"
    AMOUNT_BELOW_EXPECTED = "amount_below_expected"
    TX_NOT_ON_CHAIN_YET = "tx_not_on_chain_yet"
    TX_REPLACEABLE_STILL_PENDING = "tx_replaceable_still_pending"
    TXID_ALREADY_USED = "txid_already_used"
    TX_OLDER_THAN_INVOICE = "tx_older_than_invoice"
    TX_BELOW_INVOICE_HEIGHT = "tx_below_invoice_height"
    PAYS_A_DIFFERENT_ADDRESS = "pays_a_different_address"
    UNEXPECTED_TOKEN_CONTRACT = "unexpected_token_contract"
    TXID_BELONGS_TO_ANOTHER_CHAIN = "txid_belongs_to_another_chain"
    TX_REVERTED_ON_CHAIN = "tx_reverted_on_chain"
    MALFORMED_TXID = "malformed_txid"
    MALFORMED_AMOUNT = "malformed_amount"
    MISSING_INVOICE_ID = "missing_invoice_id"
    NETWORK_NOT_CONFIGURED = "network_not_configured"
    EVERY_PROVIDER_FAILED = "every_provider_failed"
    PROVIDERS_DISAGREE = "providers_disagree"
    INTERNAL_LOOKUP_ERROR = "internal_lookup_error"
    NATIVE_TRANSFER_NOT_READABLE = "native_transfer_not_readable"
    HASH_FOUND_ON_ANOTHER_CHAIN = "hash_found_on_another_chain"
    PRICE_UNAVAILABLE = "price_unavailable"
    WRONG_ASSET_ON_RIGHT_ADDRESS = "wrong_asset_on_right_address"
    ASSET_NOT_ACCEPTED = "asset_not_accepted"


ADVICE_BY_CODE: dict[str, str] = {
    Code.PAYMENT_FINAL: "deliver the order and mark it paid",
    Code.PAYMENT_SEEN_IN_MEMPOOL: "start the work, keep polling until final",
    Code.AMOUNT_BELOW_EXPECTED: "ask the client to top up the difference",
    Code.TX_NOT_ON_CHAIN_YET: "ask the client to wait, then retry",
    Code.TX_REPLACEABLE_STILL_PENDING: "wait for a block before delivering",
    Code.TXID_ALREADY_USED: "reject, the hash belongs to another order",
    Code.TX_OLDER_THAN_INVOICE: "reject as a replayed payment",
    Code.TX_BELOW_INVOICE_HEIGHT: "reject as a replayed payment",
    Code.PAYS_A_DIFFERENT_ADDRESS: "reject and resend the correct address",
    Code.UNEXPECTED_TOKEN_CONTRACT: "reject and name the token you accept",
    Code.TXID_BELONGS_TO_ANOTHER_CHAIN: "reject and name the correct network",
    Code.TX_REVERTED_ON_CHAIN: "ask for a fresh payment",
    Code.MALFORMED_TXID: "ask the client to resend the hash",
    Code.MALFORMED_AMOUNT: "fix the call, the amount must be positive",
    Code.MISSING_INVOICE_ID: "fix the call, an invoice id is required",
    Code.NETWORK_NOT_CONFIGURED: "set the deposit address for this network",
    Code.EVERY_PROVIDER_FAILED: "retry shortly, do not reject the client",
    Code.PROVIDERS_DISAGREE: "retry shortly, never guess on conflict",
    Code.INTERNAL_LOOKUP_ERROR: "retry shortly, check the cryptoverify log",
    Code.NATIVE_TRANSFER_NOT_READABLE: "check the transaction on etherscan.io by hand, funds may have arrived as an internal transfer",
    Code.HASH_FOUND_ON_ANOTHER_CHAIN: "reject and name the network the payment actually landed on",
    Code.PRICE_UNAVAILABLE: "retry in a moment, never invoice on a stale rate",
    Code.WRONG_ASSET_ON_RIGHT_ADDRESS: "forward the message to the client, it names the asset and menu option that actually paid",
    Code.ASSET_NOT_ACCEPTED: "the payment landed on a chain you have not configured, decide manually before delivering",
}


def advice_for(code: str) -> str:
    return ADVICE_BY_CODE.get(code, "inspect result.raw and retry")
