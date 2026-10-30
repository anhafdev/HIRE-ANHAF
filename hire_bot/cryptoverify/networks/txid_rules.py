from __future__ import annotations

import re

from ..models import Network

HEX_64 = re.compile(r"^[0-9a-fA-F]{64}$")
EVM_ONLY_NETWORKS = (Network.USDT_BEP20, Network.ETH, Network.USDT_ERC20)
BARE_HEX_NETWORKS = (Network.BTC, Network.USDT_TRC20) + EVM_ONLY_NETWORKS


def strip_txid(raw_value: str | None) -> str:
    if not raw_value:
        return ""
    return raw_value.strip().replace(" ", "")


def looks_like_hash(raw_value: str) -> bool:
    cleaned = strip_txid(raw_value)
    if cleaned.lower().startswith("0x"):
        cleaned = cleaned[2:]
    return bool(HEX_64.match(cleaned))


def carries_evm_prefix(raw_value: str) -> bool:
    return strip_txid(raw_value).lower().startswith("0x")


def networks_matching_shape(raw_value: str) -> list[Network]:
    if not looks_like_hash(raw_value):
        return []
    if carries_evm_prefix(raw_value):
        return list(EVM_ONLY_NETWORKS)
    return list(BARE_HEX_NETWORKS)


def format_for_network(raw_value: str, network: Network) -> str:
    cleaned = strip_txid(raw_value)
    if cleaned.lower().startswith("0x"):
        cleaned = cleaned[2:]
    core = cleaned.lower()
    if network in EVM_ONLY_NETWORKS:
        return "0x" + core
    return core


def inspect_txid(raw_value: str, network: Network) -> tuple[str | None, Network | None]:
    if not looks_like_hash(raw_value):
        return None, None
    allowed = networks_matching_shape(raw_value)
    if network in allowed:
        return format_for_network(raw_value, network), None
    return None, allowed[0] if allowed else None
