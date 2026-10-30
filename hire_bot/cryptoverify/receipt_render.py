from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .receipt import Receipt


def render_markdown(receipt: Receipt) -> str:
    lines = [
        f"# {receipt.brand_name} - Payment Receipt",
        "",
        f"- Receipt: `{receipt.receipt_no}`",
        f"- Invoice: `{receipt.invoice_id}`",
        f"- Date: {receipt.issued_at:%Y-%m-%d %H:%M UTC}",
        f"- Network: {receipt.network_label}",
        f"- Status: **{receipt.status}**",
        f"- Paid: **{receipt.coin_amount} {receipt.asset}**",
    ]
    if receipt.usd_amount is not None:
        lines.append(f"- Invoiced: ${receipt.usd_amount} USD")
    if receipt.locked_rate is not None:
        lines.append(
            f"- Locked rate: 1 {receipt.asset} = ${receipt.locked_rate} ({receipt.rate_source}, {receipt.rate_quote_currency} quote)"
        )
    lines += ["", "| Transaction | Amount |", "| --- | --- |"]
    for txid, amount in receipt.payments:
        lines.append(f"| `{txid}` | {amount} {receipt.asset} |")
    lines.append("")
    tail = f"Confirmations: {receipt.confirmations}"
    if receipt.block_height is not None:
        tail += f", block {receipt.block_height}"
    if receipt.provider_used:
        tail += f", via {receipt.provider_used}"
    lines.append(tail)
    return "\n".join(lines)


def render_html(receipt: Receipt) -> str:
    payment_rows = "".join(
        f'<tr><td style="font-family:monospace;padding:4px 8px">{txid}</td>'
        f'<td style="padding:4px 8px;text-align:right">{amount} {receipt.asset}</td></tr>'
        for txid, amount in receipt.payments
    )
    usd_row = (
        f'<p style="margin:4px 0">Invoiced: ${receipt.usd_amount} USD</p>' if receipt.usd_amount is not None else ""
    )
    rate_row = (
        f'<p style="margin:4px 0">Locked rate: 1 {receipt.asset} = ${receipt.locked_rate}'
        f" ({receipt.rate_source}, {receipt.rate_quote_currency} quote)</p>"
        if receipt.locked_rate is not None
        else ""
    )
    return (
        '<div style="max-width:480px;border:1px solid #ccc;border-radius:8px;'
        'padding:16px;font-family:Arial,sans-serif;color:#222">'
        f'<h2 style="margin:0 0 8px">{receipt.brand_name}</h2>'
        f'<p style="margin:4px 0">Receipt {receipt.receipt_no} for invoice {receipt.invoice_id}</p>'
        f'<p style="margin:4px 0">{receipt.issued_at:%Y-%m-%d %H:%M UTC} - {receipt.network_label} - {receipt.status}</p>'
        f'<p style="margin:8px 0;font-size:1.2em"><strong>{receipt.coin_amount} {receipt.asset}</strong></p>'
        f"{usd_row}{rate_row}"
        f'<table style="border-collapse:collapse;width:100%;margin:8px 0">{payment_rows}</table>'
        f'<p style="margin:4px 0;color:#666">Confirmations {receipt.confirmations}'
        + (f", block {receipt.block_height}" if receipt.block_height is not None else "")
        + (f", via {receipt.provider_used}" if receipt.provider_used else "")
        + "</p></div>"
    )
