from __future__ import annotations

from decimal import Decimal

from .assessment import build_result
from .chain_reader import EVM_CHAIN_NAMES, ChainReader
from .checkout import NETWORK_UNITS
from .codes import Code
from .config import Config
from .models import ChainTransaction, Network, VerifyResult, VerifyStatus


def unreadable_native_result(
    network: Network, transaction: ChainTransaction, invoice_id: str, amount: Decimal
) -> VerifyResult | None:
    if network is not Network.ETH or not transaction.raw.get("native_transfer_unreadable"):
        return None
    return build_result(
        VerifyStatus.PROVIDER_UNAVAILABLE,
        Code.NATIVE_TRANSFER_NOT_READABLE,
        "This transaction exists on chain, but the ETH movement cannot be read from a public node. "
        "Check it manually on a block explorer such as etherscan.io.",
        network=network,
        invoice_id=invoice_id,
        txid=transaction.txid,
        expected_amount=amount,
        confirmations=transaction.confirmations,
        block_height=transaction.block_height,
        block_time=transaction.block_time,
        provider_used=transaction.reported_by,
        raw=transaction.raw,
    )


async def hash_on_other_chain_result(
    reader: ChainReader,
    config: Config,
    network: Network,
    txid: str,
    invoice_id: str,
    amount: Decimal,
) -> VerifyResult | None:
    if not config.probe_other_chains or network not in EVM_CHAIN_NAMES:
        return None
    try:
        landed_on = await reader.find_hash_on_other_chains(network, txid)
    except Exception:
        return None
    if landed_on is None:
        return None
    home_chain = EVM_CHAIN_NAMES[network]
    unit = NETWORK_UNITS[network]
    return build_result(
        VerifyStatus.WRONG_NETWORK,
        Code.HASH_FOUND_ON_ANOTHER_CHAIN,
        f"This hash is a confirmed transaction on {EVM_CHAIN_NAMES[landed_on]}, not {home_chain}. "
        f"Send {unit} on the {home_chain} network instead.",
        network=network,
        invoice_id=invoice_id,
        txid=txid,
        expected_amount=amount,
    )
