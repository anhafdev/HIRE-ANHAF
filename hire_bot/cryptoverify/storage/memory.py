from __future__ import annotations

import asyncio
import time
from typing import Any

from .base import cache_key, claim_key


class MemoryStorage:
    def __init__(self) -> None:
        self._claims: dict[str, str] = {}
        self._results: dict[str, tuple[float, dict[str, Any]]] = {}
        self._tips: dict[str, int] = {}
        self._quotes: dict[str, dict[str, Any]] = {}
        self._payments: dict[str, dict[str, str]] = {}
        self._lock = asyncio.Lock()

    async def prepare(self) -> None:
        return None

    async def claim_txid(self, network: str, txid: str, invoice_id: str) -> str | None:
        async with self._lock:
            key = claim_key(network, txid)
            existing = self._claims.get(key)
            if existing is not None:
                return None if existing == invoice_id else existing
            self._claims[key] = invoice_id
            return None

    async def owner_of_txid(self, network: str, txid: str) -> str | None:
        async with self._lock:
            return self._claims.get(claim_key(network, txid))

    async def remember_result(self, invoice_id: str, network: str, txid: str, payload: dict[str, Any], ttl_seconds: int) -> None:
        async with self._lock:
            self._results[cache_key(invoice_id, network, txid)] = (time.time() + ttl_seconds, payload)

    async def recall_result(self, invoice_id: str, network: str, txid: str) -> dict[str, Any] | None:
        async with self._lock:
            entry = self._results.get(cache_key(invoice_id, network, txid))
            if entry is None:
                return None
            expires_at, payload = entry
            if expires_at < time.time():
                self._results.pop(cache_key(invoice_id, network, txid), None)
                return None
            return payload

    async def remember_invoice_tip(self, invoice_id: str, network: str, height: int) -> None:
        async with self._lock:
            self._tips.setdefault(f"{invoice_id}|{network}", height)

    async def recall_invoice_tip(self, invoice_id: str, network: str) -> int | None:
        async with self._lock:
            return self._tips.get(f"{invoice_id}|{network}")

    async def remember_invoice_quote(self, invoice_id: str, network: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            self._quotes.setdefault(f"{invoice_id}|{network}", payload)

    async def recall_invoice_quote(self, invoice_id: str, network: str) -> dict[str, Any] | None:
        async with self._lock:
            return self._quotes.get(f"{invoice_id}|{network}")

    async def remember_invoice_payment(self, invoice_id: str, network: str, txid: str, amount: str) -> None:
        async with self._lock:
            self._payments.setdefault(f"{invoice_id}|{network}", {}).setdefault(txid, amount)

    async def recall_invoice_payments(self, invoice_id: str, network: str) -> list[tuple[str, str]]:
        async with self._lock:
            entries = self._payments.get(f"{invoice_id}|{network}", {})
            return list(entries.items())

    async def close(self) -> None:
        return None
