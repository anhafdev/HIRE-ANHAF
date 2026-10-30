from __future__ import annotations

import base58
from eth_utils import is_address, is_checksum_address, to_checksum_address

BECH32_ALPHABET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
BECH32_CONSTANT = 1
BECH32M_CONSTANT = 0x2BC830A3
BASE58_BTC_VERSIONS = {0x00, 0x05, 0x6F, 0xC4}
TRON_VERSION_BYTE = 0x41
BITCOIN_PREFIXES = {"bc", "tb", "bcrt"}


def _fold_checksum(values: list[int]) -> int:
    generator = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    checksum = 1
    for value in values:
        top = checksum >> 25
        checksum = ((checksum & 0x1FFFFFF) << 5) ^ value
        for index in range(5):
            checksum ^= generator[index] if ((top >> index) & 1) else 0
    return checksum


def _spread_prefix(prefix: str) -> list[int]:
    return [ord(char) >> 5 for char in prefix] + [0] + [ord(char) & 31 for char in prefix]


def read_bech32(address: str) -> tuple[str, list[int], int] | None:
    if any(ord(char) < 33 or ord(char) > 126 for char in address):
        return None
    lowered = address.lower()
    if lowered != address and address.upper() != address:
        return None
    split_at = lowered.rfind("1")
    if split_at < 1 or split_at + 7 > len(lowered) or len(lowered) > 90:
        return None
    prefix = lowered[:split_at]
    body = []
    for char in lowered[split_at + 1 :]:
        if char not in BECH32_ALPHABET:
            return None
        body.append(BECH32_ALPHABET.index(char))
    checksum = _fold_checksum(_spread_prefix(prefix) + body)
    if checksum not in (BECH32_CONSTANT, BECH32M_CONSTANT):
        return None
    return prefix, body[:-6], checksum


def is_valid_bitcoin_address(address: str) -> bool:
    if not address:
        return False
    decoded = read_bech32(address)
    if decoded is not None:
        prefix, payload, checksum = decoded
        if prefix not in BITCOIN_PREFIXES or not payload:
            return False
        witness_version = payload[0]
        if witness_version == 0 and checksum != BECH32_CONSTANT:
            return False
        if witness_version > 0 and checksum != BECH32M_CONSTANT:
            return False
        return 0 <= witness_version <= 16
    try:
        payload_bytes = base58.b58decode_check(address)
    except Exception:
        return False
    return len(payload_bytes) == 21 and payload_bytes[0] in BASE58_BTC_VERSIONS


def is_valid_tron_address(address: str) -> bool:
    if not address or not address.startswith("T"):
        return False
    try:
        payload_bytes = base58.b58decode_check(address)
    except Exception:
        return False
    return len(payload_bytes) == 21 and payload_bytes[0] == TRON_VERSION_BYTE


def is_valid_evm_address(address: str) -> bool:
    if not address or not is_address(address):
        return False
    stripped = address[2:] if address.lower().startswith("0x") else address
    if stripped.islower() or stripped.isupper():
        return True
    return is_checksum_address(address)


def tron_hex_to_base58(raw_value: str) -> str:
    cleaned = raw_value.lower().removeprefix("0x")
    if len(cleaned) >= 40:
        cleaned = cleaned[-40:]
    body = bytes([TRON_VERSION_BYTE]) + bytes.fromhex(cleaned)
    return base58.b58encode_check(body).decode()


def normalize_tron_address(raw_value: str) -> str:
    if not raw_value:
        return ""
    if raw_value.startswith("T") and is_valid_tron_address(raw_value):
        return raw_value
    try:
        return tron_hex_to_base58(raw_value)
    except Exception:
        return raw_value


def evm_topic_to_address(topic: str) -> str:
    cleaned = topic.lower().removeprefix("0x")
    return to_checksum_address("0x" + cleaned[-40:])


def normalize_evm_address(raw_value: str) -> str:
    try:
        return to_checksum_address(raw_value)
    except Exception:
        return raw_value


def same_address(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    if left.startswith("T") or right.startswith("T"):
        return left == right
    return left.lower() == right.lower()
