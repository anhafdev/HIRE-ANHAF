from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from .checkout_models import INVOICE_ALPHABET
from .models import right_now
from .pricing import trim_zeros

logger = logging.getLogger("cryptoverify.receipt")

BOX_WIDTH = 62


def new_receipt_no(prefix: str) -> str:
    tail = "".join(secrets.choice(INVOICE_ALPHABET) for _ in range(5))
    return f"{prefix}-{right_now():%Y%m%d}-{tail}"


def short_hash(txid: str) -> str:
    return txid if len(txid) <= 14 else f"{txid[:6]}...{txid[-4:]}"


@dataclass
class Receipt:
    receipt_no: str
    invoice_id: str
    brand_name: str
    issued_at: datetime
    network_label: str
    asset: str
    usd_amount: Decimal | None
    coin_amount: Decimal
    locked_rate: Decimal | None
    rate_source: str
    rate_quote_currency: str
    payments: list[tuple[str, Decimal]]
    confirmations: int
    block_height: int | None
    provider_used: str
    status: str
    brand_tagline: str = ""
    brand_support: str = ""
    brand_website: str = ""

    def body_lines(self) -> list[str]:
        rows = [
            f"Receipt   {self.receipt_no}",
            f"Invoice   {self.invoice_id}",
            f"Date      {self.issued_at:%Y-%m-%d %H:%M UTC}",
            f"Network   {self.network_label}",
            f"Status    {self.status}",
            "",
            f"Paid      {self.coin_amount} {self.asset}",
        ]
        if self.usd_amount is not None:
            rows.append(f"Invoiced  ${self.usd_amount} USD")
        if self.locked_rate is not None:
            rows.append(f"Rate      1 {self.asset} = ${self.locked_rate} ({self.rate_source}, {self.rate_quote_currency} quote)")
        rows.append("")
        rows.append("Payments:")
        for txid, amount in self.payments:
            rows.append(f"  {short_hash(txid)}  {amount} {self.asset}")
        rows.append("")
        tail = f"Confirmations {self.confirmations}"
        if self.block_height is not None:
            tail += f"  Block {self.block_height}"
        if self.provider_used:
            tail += f"  via {self.provider_used}"
        rows.append(tail)
        return rows

    def as_text(self) -> str:
        edge = "+" + "-" * (BOX_WIDTH - 2) + "+"
        lines = [edge, boxed(self.brand_name.upper())]
        if self.brand_tagline:
            lines.append(boxed(self.brand_tagline))
        lines.append(edge)
        for row in self.body_lines():
            lines.append(boxed(row))
        footer = [line for line in (self.brand_support, self.brand_website) if line]
        if footer:
            lines.append(edge)
            lines.extend(boxed(line) for line in footer)
        lines.append(edge)
        return "\n".join(lines)

    def as_markdown(self) -> str:
        from .receipt_render import render_markdown

        return render_markdown(self)

    def as_html(self) -> str:
        from .receipt_render import render_html

        return render_html(self)


def boxed(text: str) -> str:
    inner = text[: BOX_WIDTH - 4]
    return "| " + inner.ljust(BOX_WIDTH - 4) + " |"


def build_receipt(session: Any, result: Any) -> Receipt:
    config = session.config
    request = session.request
    payments = list(session.payments)
    if not payments and result.amount is not None:
        payments = [(result.txid, result.amount)]
    return Receipt(
        receipt_no=new_receipt_no(config.brand_receipt_prefix or "RCP"),
        invoice_id=session.invoice_id,
        brand_name=config.brand_name or "cryptoverify",
        issued_at=right_now(),
        network_label=request.label if request else "",
        asset=request.unit if request else "",
        usd_amount=session.usd_amount,
        coin_amount=trim_zeros(result.amount) if result.amount is not None else (request.amount if request else Decimal(0)),
        locked_rate=session.quote.price if session.quote else None,
        rate_source=session.quote.source if session.quote else "",
        rate_quote_currency=session.quote.quote_currency if session.quote else "",
        payments=payments,
        confirmations=result.confirmations,
        block_height=result.block_height,
        provider_used=result.provider_used or "",
        status=result.status.value,
        brand_tagline=config.brand_tagline,
        brand_support=config.brand_support,
        brand_website=config.brand_website,
    )


def save_receipt_files(receipt: Receipt, directory: str) -> None:
    try:
        folder = Path(directory)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{receipt.receipt_no}.txt").write_text(receipt.as_text(), encoding="utf-8")
        (folder / f"{receipt.receipt_no}.md").write_text(receipt.as_markdown(), encoding="utf-8")
    except Exception:
        logger.warning("could not write the receipt files to %s", directory)
