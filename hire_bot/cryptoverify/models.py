from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from .codes import Code


class Network(str, Enum):
    BTC = "BTC"
    USDT_TRC20 = "USDT_TRC20"
    USDT_BEP20 = "USDT_BEP20"
    ETH = "ETH"
    USDT_ERC20 = "USDT_ERC20"


class VerifyStatus(str, Enum):
    DETECTED = "DETECTED"
    CONFIRMED = "CONFIRMED"
    UNDERPAID = "UNDERPAID"
    NOT_FOUND = "NOT_FOUND"
    REUSED = "REUSED"
    STALE = "STALE"
    WRONG_ADDRESS = "WRONG_ADDRESS"
    WRONG_TOKEN = "WRONG_TOKEN"
    WRONG_NETWORK = "WRONG_NETWORK"
    FAILED_TX = "FAILED_TX"
    INVALID_INPUT = "INVALID_INPUT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"


class Tier(int, Enum):
    NONE = 0
    DETECTED = 1
    CONFIRMED = 2


DECIMALS_BY_NETWORK: dict[Network, int] = {
    Network.BTC: 8,
    Network.USDT_TRC20: 6,
    Network.USDT_BEP20: 18,
    Network.ETH: 18,
    Network.USDT_ERC20: 6,
}

TOKEN_CONTRACT_BY_NETWORK: dict[Network, str] = {
    Network.USDT_TRC20: "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
    Network.USDT_BEP20: "0x55d398326f99059fF775485246999027B3197955",
    Network.USDT_ERC20: "0xdAC17F958D2ee523a2206206994597C13D831ec7",
}

TIER_BY_STATUS: dict[VerifyStatus, Tier] = {
    VerifyStatus.DETECTED: Tier.DETECTED,
    VerifyStatus.CONFIRMED: Tier.CONFIRMED,
}


def right_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class TokenTransfer:
    recipient: str
    amount: Decimal
    contract: str | None = None


@dataclass
class ProviderError:
    provider: str
    reason: str

    def as_text(self) -> str:
        return f"{self.provider}: {self.reason}"


@dataclass
class ChainTransaction:
    txid: str
    network: Network
    found: bool = False
    succeeded: bool = True
    settled_in_block: bool = False
    confirmations: int = 0
    block_height: int | None = None
    block_time: datetime | None = None
    first_seen_at: datetime | None = None
    replaceable: bool = False
    transfers: list[TokenTransfer] = field(default_factory=list)
    contracts_touched: list[str] = field(default_factory=list)
    tip_height: int | None = None
    reported_by: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def money_fingerprint(self) -> tuple:
        moves = sorted(
            (
                (item.contract or "").lower(),
                item.recipient.lower(),
                str(item.amount),
            )
            for item in self.transfers
        )
        return (self.found, self.succeeded, tuple(moves))

    def happened_at(self) -> datetime | None:
        return self.block_time or self.first_seen_at


@dataclass
class VerifyResult:
    status: VerifyStatus
    code: str
    message: str
    network: Network | None = None
    txid: str = ""
    invoice_id: str = ""
    amount: Decimal | None = None
    expected_amount: Decimal | None = None
    surplus: Decimal | None = None
    confirmations: int = 0
    required_confirmations: int = 0
    block_height: int | None = None
    block_time: datetime | None = None
    rbf_risk: bool = False
    claimed_by_invoice: str | None = None
    provider_used: str | None = None
    provider_errors: list[ProviderError] = field(default_factory=list)
    checked_at: datetime = field(default_factory=right_now)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def tier(self) -> Tier:
        return TIER_BY_STATUS.get(self.status, Tier.NONE)

    def is_acceptable(self, min_tier: Tier = Tier.DETECTED) -> bool:
        return self.tier.value >= min_tier.value

    def is_final(self) -> bool:
        return self.status is VerifyStatus.CONFIRMED

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "code": self.code,
            "message": self.message,
            "network": self.network.value if self.network else None,
            "txid": self.txid,
            "invoice_id": self.invoice_id,
            "amount": str(self.amount) if self.amount is not None else None,
            "expected_amount": str(self.expected_amount) if self.expected_amount is not None else None,
            "surplus": str(self.surplus) if self.surplus is not None else None,
            "confirmations": self.confirmations,
            "required_confirmations": self.required_confirmations,
            "block_height": self.block_height,
            "block_time": self.block_time.isoformat() if self.block_time else None,
            "rbf_risk": self.rbf_risk,
            "claimed_by_invoice": self.claimed_by_invoice,
            "provider_used": self.provider_used,
            "checked_at": self.checked_at.isoformat(),
        }


def result_from_dict(payload: dict[str, Any]) -> VerifyResult:
    return VerifyResult(
        status=VerifyStatus(payload["status"]),
        code=payload["code"],
        message=payload["message"],
        network=Network(payload["network"]) if payload.get("network") else None,
        txid=payload.get("txid", ""),
        invoice_id=payload.get("invoice_id", ""),
        amount=Decimal(payload["amount"]) if payload.get("amount") else None,
        expected_amount=Decimal(payload["expected_amount"]) if payload.get("expected_amount") else None,
        surplus=Decimal(payload["surplus"]) if payload.get("surplus") else None,
        confirmations=payload.get("confirmations", 0),
        required_confirmations=payload.get("required_confirmations", 0),
        block_height=payload.get("block_height"),
        block_time=datetime.fromisoformat(payload["block_time"]) if payload.get("block_time") else None,
        rbf_risk=payload.get("rbf_risk", False),
        claimed_by_invoice=payload.get("claimed_by_invoice"),
        provider_used=payload.get("provider_used"),
        checked_at=datetime.fromisoformat(payload["checked_at"]),
    )
