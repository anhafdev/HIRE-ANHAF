from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from typing import Any, Awaitable, Callable

from .config import Config
from .models import DECIMALS_BY_NETWORK, Network
from .providers.http_client import HttpSession
from .providers.prices import PriceAnswer, price_readers

PRICE_SYMBOLS = {Network.BTC: "BTC", Network.ETH: "ETH"}
CENT = Decimal("0.01")


@dataclass
class PriceQuote:
    price: Decimal
    source: str
    quote_currency: str
    quote_is_thin: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "price": str(self.price),
            "source": self.source,
            "quote_currency": self.quote_currency,
            "quote_is_thin": self.quote_is_thin,
        }


def quote_from_payload(payload: dict[str, Any] | None) -> PriceQuote | None:
    if not payload or not payload.get("price"):
        return None
    return PriceQuote(
        price=Decimal(str(payload["price"])),
        source=str(payload.get("source") or ""),
        quote_currency=str(payload.get("quote_currency") or "USD"),
        quote_is_thin=bool(payload.get("quote_is_thin", False)),
    )


def middle_price(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    halfway = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[halfway]
    return (ordered[halfway - 1] + ordered[halfway]) / 2


def pick_conservative_quote(answers: list[PriceAnswer], max_spread_percent: Decimal) -> PriceQuote | None:
    if not answers:
        return None
    center = middle_price([price for price, _, _ in answers])
    survivors = [
        item for item in answers if center > 0 and (abs(item[0] - center) / center) * 100 <= max_spread_percent
    ]
    if not survivors:
        return None
    price, source, currency = min(survivors, key=lambda item: item[0])
    return PriceQuote(price=price, source=source, quote_currency=currency, quote_is_thin=len(answers) < 2)


async def ask_price_sources(
    readers: list[tuple[str, Callable[[], Awaitable[PriceAnswer]]]], timeout_seconds: float
) -> list[PriceAnswer]:
    async def one(factory: Callable[[], Awaitable[PriceAnswer]]) -> PriceAnswer | None:
        try:
            return await asyncio.wait_for(factory(), timeout_seconds)
        except Exception:
            return None

    collected = await asyncio.gather(*(one(factory) for _, factory in readers))
    return [item for item in collected if item is not None]


async def fetch_usd_price(session: HttpSession, config: Config, network: Network) -> PriceQuote | None:
    symbol = PRICE_SYMBOLS.get(network)
    if symbol is None:
        rate = config.usdt_usd_rate
        return PriceQuote(price=rate, source="fixed", quote_currency="USD") if rate > 0 else None
    readers = price_readers(session, symbol)
    answers = await ask_price_sources(readers[:3], config.price_timeout_seconds)
    if len(answers) < 2:
        answers += await ask_price_sources(readers[3:], config.price_timeout_seconds)
    return pick_conservative_quote(answers, config.price_max_spread_percent)


def trim_zeros(value: Decimal) -> Decimal:
    trimmed = value.normalize()
    return trimmed.quantize(Decimal(1)) if trimmed.as_tuple().exponent > 0 else trimmed


def required_coin_for(usd_amount: Decimal, quote: PriceQuote, network: Network, config: Config) -> Decimal:
    padded = usd_amount * (Decimal(1) + config.price_safety_percent / Decimal(100))
    step = Decimal(1).scaleb(-DECIMALS_BY_NETWORK[network])
    return trim_zeros((padded / quote.price).quantize(step, rounding=ROUND_CEILING))


def usd_value(coin_amount: Decimal, quote: PriceQuote) -> Decimal:
    return (coin_amount * quote.price).quantize(CENT)


def describe_shortfall(received: Decimal, required: Decimal, quote: PriceQuote | None) -> str:
    missing = required - received
    if quote is None:
        return f"We received {received} but expected {required}. Short by {missing}."
    return (
        f"We received {received} (about ${usd_value(received, quote)}) but this invoice needs "
        f"{required} (${usd_value(required, quote)}). Short by {missing} (about ${usd_value(missing, quote)})."
    )
