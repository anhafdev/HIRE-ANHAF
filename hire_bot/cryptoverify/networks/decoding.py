from __future__ import annotations

from decimal import Decimal
from typing import Any

from eth_utils import keccak

from ..models import TokenTransfer
from .addresses import evm_topic_to_address, normalize_evm_address, normalize_tron_address

TRANSFER_SIGNATURE = "Transfer(address,address,uint256)"
TRANSFER_SELECTOR = "a9059cbb"
TRANSFER_FROM_SELECTOR = "23b872dd"


def transfer_event_topic() -> str:
    return "0x" + keccak(text=TRANSFER_SIGNATURE).hex()


def scale_units(raw_value: int | str, decimals: int) -> Decimal:
    return Decimal(int(raw_value)).scaleb(-decimals)


def read_hex_int(raw_value: Any, fallback: int = 0) -> int:
    if raw_value is None:
        return fallback
    if isinstance(raw_value, int):
        return raw_value
    text = str(raw_value).strip()
    if not text:
        return fallback
    try:
        return int(text, 16) if text.lower().startswith("0x") else int(text)
    except ValueError:
        return fallback


def matches_transfer_topic(topics: list[str]) -> bool:
    if not topics or len(topics) < 3:
        return False
    head = topics[0].lower()
    head = head if head.startswith("0x") else "0x" + head
    return head == transfer_event_topic()


def read_evm_transfer_logs(logs: list[dict[str, Any]], decimals: int) -> list[TokenTransfer]:
    collected: list[TokenTransfer] = []
    for entry in logs or []:
        topics = [str(item) for item in (entry.get("topics") or [])]
        if not matches_transfer_topic(topics):
            continue
        try:
            recipient = evm_topic_to_address(topics[2])
        except Exception:
            continue
        amount_raw = read_hex_int(entry.get("data"), 0)
        contract = normalize_evm_address(str(entry.get("address") or ""))
        collected.append(TokenTransfer(recipient=recipient, amount=scale_units(amount_raw, decimals), contract=contract))
    return collected


def read_tron_transfer_logs(logs: list[dict[str, Any]], decimals: int) -> list[TokenTransfer]:
    collected: list[TokenTransfer] = []
    for entry in logs or []:
        topics = [str(item) for item in (entry.get("topics") or [])]
        if not matches_transfer_topic(topics):
            continue
        recipient = normalize_tron_address(topics[2])
        amount_raw = read_hex_int("0x" + str(entry.get("data") or "0").removeprefix("0x"), 0)
        contract = normalize_tron_address(str(entry.get("address") or ""))
        collected.append(TokenTransfer(recipient=recipient, amount=scale_units(amount_raw, decimals), contract=contract))
    return collected


def read_tronscan_transfers(entries: list[dict[str, Any]]) -> list[TokenTransfer]:
    collected: list[TokenTransfer] = []
    for entry in entries or []:
        recipient = normalize_tron_address(str(entry.get("to_address") or entry.get("toAddress") or ""))
        contract = normalize_tron_address(str(entry.get("contract_address") or entry.get("contractAddress") or ""))
        decimals = int(entry.get("decimals") or 6)
        amount_raw = entry.get("amount_str") or entry.get("amount") or entry.get("quant") or 0
        collected.append(TokenTransfer(recipient=recipient, amount=scale_units(amount_raw, decimals), contract=contract))
    return collected


def decode_transfer_calldata(data_hex: str | None, decimals: int) -> tuple[str, Decimal] | None:
    cleaned = (data_hex or "").lower().removeprefix("0x")
    if len(cleaned) < 8:
        return None
    selector, body = cleaned[:8], cleaned[8:]
    try:
        if selector == TRANSFER_SELECTOR and len(body) >= 128:
            return body[0:64], scale_units(int(body[64:128], 16), decimals)
        if selector == TRANSFER_FROM_SELECTOR and len(body) >= 192:
            return body[64:128], scale_units(int(body[128:192], 16), decimals)
    except ValueError:
        return None
    return None


def read_pending_evm_transfer(to_field: str | None, data_hex: str | None, decimals: int) -> list[TokenTransfer]:
    decoded = decode_transfer_calldata(data_hex, decimals)
    if decoded is None or not to_field:
        return []
    word, amount = decoded
    return [TokenTransfer(recipient=evm_topic_to_address(word), amount=amount, contract=normalize_evm_address(to_field))]


def read_pending_tron_transfer(contract_field: str | None, data_hex: str | None, decimals: int) -> list[TokenTransfer]:
    decoded = decode_transfer_calldata(data_hex, decimals)
    if decoded is None or not contract_field:
        return []
    word, amount = decoded
    return [
        TokenTransfer(
            recipient=normalize_tron_address(word),
            amount=amount,
            contract=normalize_tron_address(contract_field),
        )
    ]


def read_bitcoin_outputs(outputs: list[dict[str, Any]], decimals: int) -> list[TokenTransfer]:
    collected: list[TokenTransfer] = []
    for entry in outputs or []:
        recipient = entry.get("scriptpubkey_address") or entry.get("addr") or ""
        if not recipient:
            continue
        satoshis = int(entry.get("value") or 0)
        collected.append(TokenTransfer(recipient=str(recipient), amount=scale_units(satoshis, decimals), contract=None))
    return collected


def signals_replace_by_fee(inputs: list[dict[str, Any]]) -> bool:
    for entry in inputs or []:
        sequence = entry.get("sequence")
        if sequence is None:
            continue
        if int(sequence) < 0xFFFFFFFE:
            return True
    return False


def total_paid_to(transfers: list[TokenTransfer], address: str, contract: str | None) -> Decimal:
    from .addresses import same_address

    running = Decimal(0)
    for item in transfers:
        if contract is not None and not same_address(item.contract, contract):
            continue
        if same_address(item.recipient, address):
            running += item.amount
    return running
