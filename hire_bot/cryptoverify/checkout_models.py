from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum

from .models import Network, right_now

CENT = Decimal("0.01")
EIGHT_PLACES = Decimal("1E-8")


def usd_text(value: Decimal) -> str:
    cents = value.quantize(CENT)
    return str(cents) if cents == value else str(value)


def confirmations_text(confirmations: int, required: int) -> str:
    if confirmations > required:
        return f"{confirmations} (need {required})"
    return f"{confirmations}/{required}"


def display_amount(value: Decimal) -> Decimal:
    rounded = value.quantize(EIGHT_PLACES) if value.as_tuple().exponent < -8 else value
    trimmed = rounded.normalize()
    return trimmed.quantize(Decimal(1)) if trimmed.as_tuple().exponent > 0 else trimmed

INVOICE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

NETWORK_LABELS: dict[Network, str] = {
    Network.BTC: "Bitcoin (BTC)",
    Network.USDT_TRC20: "USDT on TRON (TRC20)",
    Network.USDT_BEP20: "USDT on BSC (BEP20)",
    Network.ETH: "Ethereum (ETH)",
    Network.USDT_ERC20: "USDT on Ethereum (ERC20)",
}

NETWORK_UNITS: dict[Network, str] = {
    Network.BTC: "BTC",
    Network.USDT_TRC20: "USDT",
    Network.USDT_BEP20: "USDT",
    Network.ETH: "ETH",
    Network.USDT_ERC20: "USDT",
}


def new_invoice_id(prefix: str = "INV") -> str:
    tail = "".join(secrets.choice(INVOICE_ALPHABET) for _ in range(5))
    return f"{prefix}-{tail}"


class CheckoutStep(str, Enum):
    PICK_NETWORK = "pick_network"
    ENTER_AMOUNT = "enter_amount"
    SHOW_ADDRESS = "show_address"
    AWAIT_TXID = "await_txid"
    DONE = "done"


@dataclass
class StepOutcome:
    ok: bool
    step: CheckoutStep
    message: str = ""
    code: str = ""


@dataclass
class AcceptedOption:
    network: Network
    label: str
    asset: str
    address: str
    required_coin: Decimal
    token_contract: str | None = None


@dataclass
class PaymentRequest:
    invoice_id: str
    network: Network
    amount: Decimal
    address: str
    label: str
    unit: str
    created_at: datetime
    expires_at: datetime
    minimum_accepted: Decimal
    required_confirmations: int
    token_contract: str | None = None
    tip_height: int | None = None
    usd_amount: Decimal | None = None
    locked_rate: Decimal | None = None
    rate_source: str = ""
    rate_quote_currency: str = ""
    quote_is_thin: bool = False
    accepted: list[AcceptedOption] = field(default_factory=list)
    unavailable: list[Network] = field(default_factory=list)
    shared_address_with: list[Network] = field(default_factory=list)

    def is_expired(self, moment: datetime | None = None) -> bool:
        return (moment or right_now()) > self.expires_at

    def as_lines(self) -> list[str]:
        amount_row = f"Amount     {self.amount} {self.unit}"
        if self.usd_amount is not None:
            amount_row += f"  (${usd_text(self.usd_amount)})"
        rows = [
            f"Invoice    {self.invoice_id}",
            f"Network    {self.label}",
            amount_row,
        ]
        if self.usd_amount is not None and self.locked_rate is not None:
            rows.append(
                f"USD value  ${usd_text(self.usd_amount)} at 1 {self.unit} = ${usd_text(self.locked_rate)} ({self.rate_source})"
            )
        rows.append(f"Address    {self.address}")
        if self.token_contract:
            rows.append(f"Token      {self.token_contract}")
        rows.append(f"Expires    {self.expires_at.strftime('%H:%M:%S UTC')}")
        return rows
