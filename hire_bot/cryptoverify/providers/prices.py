from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Awaitable, Callable

from ..exceptions import ProviderCallFailed, ProviderResponseInvalid
from .http_client import HttpSession
from .schemas import Loose, parse_or_fail

BINANCE_VISION_URL = "https://data-api.binance.vision/api/v3/ticker/price"
BINANCE_URL = "https://api.binance.com/api/v3/ticker/price"
COINBASE_URL = "https://api.coinbase.com/v2/prices"
KRAKEN_URL = "https://api.kraken.com/0/public/Ticker"

PriceAnswer = tuple[Decimal, str, str]


class BinancePrice(Loose):
    symbol: str | None = None
    price: str


class CoinbaseAmount(Loose):
    amount: str
    currency: str = "USD"


class CoinbasePrice(Loose):
    data: CoinbaseAmount


class KrakenPrice(Loose):
    error: list[Any] = []
    result: dict[str, Any] = {}


def read_positive_price(raw_value: str, provider: str) -> Decimal:
    try:
        parsed = Decimal(str(raw_value))
    except (InvalidOperation, ValueError):
        raise ProviderResponseInvalid(provider, "price is not a number")
    if parsed <= 0:
        raise ProviderResponseInvalid(provider, "price is not positive")
    return parsed


async def read_binance_price(session: HttpSession, url: str, symbol: str, label: str) -> PriceAnswer:
    payload = await session.fetch_json(label, url, params={"symbol": f"{symbol}USDT"})
    parsed = parse_or_fail(BinancePrice, payload, label)
    return read_positive_price(parsed.price, label), label, "USDT"


async def read_coinbase_price(session: HttpSession, symbol: str) -> PriceAnswer:
    label = "coinbase"
    payload = await session.fetch_json(label, f"{COINBASE_URL}/{symbol}-USD/spot")
    parsed = parse_or_fail(CoinbasePrice, payload, label)
    return read_positive_price(parsed.data.amount, label), label, parsed.data.currency or "USD"


async def read_kraken_price(session: HttpSession, symbol: str) -> PriceAnswer:
    label = "kraken"
    payload = await session.fetch_json(label, KRAKEN_URL, params={"pair": f"{symbol}USD"})
    parsed = parse_or_fail(KrakenPrice, payload, label)
    if parsed.error:
        raise ProviderCallFailed(label, f"kraken rejected the request: {parsed.error[0]}", retryable=False)
    if len(parsed.result) != 1:
        raise ProviderResponseInvalid(label, "expected exactly one ticker pair")
    entry = next(iter(parsed.result.values()))
    closing = (entry or {}).get("c") or []
    if not closing:
        raise ProviderResponseInvalid(label, "no closing price in the ticker")
    return read_positive_price(closing[0], label), label, "USD"


def price_readers(session: HttpSession, symbol: str) -> list[tuple[str, Callable[[], Awaitable[PriceAnswer]]]]:
    return [
        ("binance.vision", lambda: read_binance_price(session, BINANCE_VISION_URL, symbol, "binance.vision")),
        ("binance.com", lambda: read_binance_price(session, BINANCE_URL, symbol, "binance.com")),
        ("coinbase", lambda: read_coinbase_price(session, symbol)),
        ("kraken", lambda: read_kraken_price(session, symbol)),
    ]
