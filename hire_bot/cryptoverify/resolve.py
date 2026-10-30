from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from decimal import Decimal

from .chain_reader import EVM_CHAIN_NAMES, ChainReader
from .checkout_models import NETWORK_UNITS
from .config import Config
from .exceptions import NoProviderAnswered
from .models import TOKEN_CONTRACT_BY_NETWORK, ChainTransaction, Network, ProviderError, TokenTransfer
from .networks.addresses import normalize_evm_address, same_address
from .networks.decoding import read_evm_transfer_logs, read_hex_int, scale_units
from .networks.txid_rules import format_for_network, looks_like_hash

CHAIN_HOMES: dict[Network, str] = {
    Network.BTC: "Bitcoin",
    Network.USDT_TRC20: "TRON",
    **EVM_CHAIN_NAMES,
}
ERC20_USDT_DECIMALS = 6
NATIVE_ETH_DECIMALS = 18


@dataclass
class AssetMovement:
    network: Network
    asset: str
    amount: Decimal
    pays_us: bool
    confirmations: int
    required_confirmations: int
    block_height: int | None
    succeeded: bool
    provider_used: str


@dataclass
class HashIdentity:
    txid: str
    found_on: list[AssetMovement] = field(default_factory=list)
    probed: list[Network] = field(default_factory=list)
    provider_errors: list[ProviderError] = field(default_factory=list)

    def movement_for(self, network: Network) -> AssetMovement | None:
        for item in self.found_on:
            if item.network is network:
                return item
        return None

    def paying_movements(self) -> list[AssetMovement]:
        return [item for item in self.found_on if item.pays_us]


def members_on_chain(home: str) -> list[Network]:
    return [item for item in Network if CHAIN_HOMES[item] == home]


def chain_groups(config: Config) -> list[tuple[str, list[Network]]]:
    groups: dict[str, list[Network]] = {}
    for network in config.enabled_networks():
        groups.setdefault(CHAIN_HOMES[network], []).append(network)
    return list(groups.items())


def reference_address(config: Config, network: Network, siblings: list[Network]) -> str:
    own = config.address_for(network)
    if own:
        return own
    for other in siblings:
        address = config.address_for(other)
        if address:
            return address
    return ""


def relevant_transfers(tx: ChainTransaction, network: Network) -> list[TokenTransfer]:
    contract = TOKEN_CONTRACT_BY_NETWORK.get(network)
    if network is tx.network:
        if contract is None:
            return [item for item in tx.transfers if item.contract is None]
        return [item for item in tx.transfers if same_address(item.contract, contract)]
    if contract is not None:
        logs = (tx.raw.get("receipt") or {}).get("logs") or []
        decoded = read_evm_transfer_logs(list(logs), ERC20_USDT_DECIMALS)
        return [item for item in decoded if same_address(item.contract, contract)]
    payload = tx.raw.get("tx") or {}
    raw_value = read_hex_int(payload.get("value"), 0)
    to_field = payload.get("to")
    if not to_field or raw_value <= 0:
        return []
    return [
        TokenTransfer(
            recipient=normalize_evm_address(str(to_field)),
            amount=scale_units(raw_value, NATIVE_ETH_DECIMALS),
            contract=None,
        )
    ]


def movement_from(tx: ChainTransaction, network: Network, config: Config, siblings: list[Network]) -> AssetMovement | None:
    moves = relevant_transfers(tx, network)
    if not moves:
        return None
    address = reference_address(config, network, siblings)
    ours = [item for item in moves if address and same_address(item.recipient, address)]
    counted = ours or moves
    amount = Decimal(0)
    for item in counted:
        amount += item.amount
    return AssetMovement(
        network=network,
        asset=NETWORK_UNITS[network],
        amount=amount,
        pays_us=bool(ours),
        confirmations=tx.confirmations,
        required_confirmations=config.min_confirmations_for(network),
        block_height=tx.block_height,
        succeeded=tx.succeeded,
        provider_used=tx.reported_by,
    )


async def identify_hash(reader: ChainReader, config: Config, txid: str) -> HashIdentity:
    identity = HashIdentity(txid=str(txid or "").strip())
    if not looks_like_hash(identity.txid):
        return identity
    groups = chain_groups(config)

    async def probe(home: str, enabled: list[Network]) -> tuple[list[AssetMovement], list[ProviderError]]:
        representative = enabled[0]
        formatted = format_for_network(identity.txid, representative)
        try:
            tx, _, failures = await reader.read_transaction(representative, formatted)
        except NoProviderAnswered as outage:
            return [], list(outage.failures)
        except Exception as error:
            return [], [ProviderError(provider=home, reason=f"unexpected {type(error).__name__}")]
        if not tx.found:
            return [], failures
        siblings = members_on_chain(home)
        collected = [movement_from(tx, item, config, siblings) for item in siblings]
        return [item for item in collected if item is not None], failures

    outcomes = await asyncio.gather(*(probe(home, networks) for home, networks in groups))
    for (_, networks), (movements, errors) in zip(groups, outcomes):
        identity.probed.extend(networks)
        identity.found_on.extend(movements)
        identity.provider_errors.extend(errors)
    return identity
