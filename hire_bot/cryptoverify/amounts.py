from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from .config import Config
from .models import DECIMALS_BY_NETWORK, ChainTransaction, Network, TokenTransfer
from .networks.addresses import same_address


def read_amount(raw_value) -> Decimal | None:
    if raw_value is None:
        return None
    try:
        parsed = Decimal(str(raw_value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed > 0 else None


def pick_transfers_for_contract(transfers: list[TokenTransfer], contract: str | None) -> list[TokenTransfer]:
    if contract is None:
        return list(transfers)
    return [item for item in transfers if same_address(item.contract, contract)]


def pick_transfers_to_address(transfers: list[TokenTransfer], address: str) -> list[TokenTransfer]:
    return [item for item in transfers if same_address(item.recipient, address)]


def add_up(transfers: list[TokenTransfer]) -> Decimal:
    total = Decimal(0)
    for item in transfers:
        total += item.amount
    return total


def smallest_unit_for(network: Network) -> Decimal:
    return Decimal(1).scaleb(-DECIMALS_BY_NETWORK[network])


def smallest_acceptable_amount(expected: Decimal, config: Config, network: Network) -> Decimal:
    if not config.allow_underpayment:
        return expected
    percentage_floor = expected * (Decimal(1) - (config.tolerance_percent / Decimal(100)))
    dust_floor = expected - config.dust_allowance_for(network)
    return min(percentage_floor, dust_floor)


def tx_predates_invoice(tx: ChainTransaction, invoice_created_at: datetime, skew_minutes: int) -> bool:
    seen_at = tx.happened_at()
    if seen_at is None or invoice_created_at is None:
        return False
    earliest_allowed = invoice_created_at - timedelta(minutes=skew_minutes)
    if seen_at.tzinfo is None:
        seen_at = seen_at.replace(tzinfo=earliest_allowed.tzinfo)
    return seen_at < earliest_allowed


def tx_below_invoice_height(tx: ChainTransaction, invoice_tip_height: int | None, reorg_buffer: int) -> bool:
    if invoice_tip_height is None or tx.block_height is None:
        return False
    return tx.block_height < (invoice_tip_height - reorg_buffer)
