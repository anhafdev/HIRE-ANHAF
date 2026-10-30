from __future__ import annotations

import json
from typing import Any

from ..exceptions import ConfigurationError
from .base import cache_key, claim_key

NAMESPACE = "cryptoverify"


class RedisStorage:
    def __init__(self, url: str = "redis://localhost:6379/0", client: Any = None) -> None:
        if client is None:
            try:
                from redis.asyncio import Redis
            except ImportError as error:
                raise ConfigurationError("RedisStorage needs the redis extra: pip install cryptoverify[redis]") from error
            client = Redis.from_url(url, decode_responses=True)
        self._client = client

    async def prepare(self) -> None:
        return None

    async def claim_txid(self, network: str, txid: str, invoice_id: str) -> str | None:
        key = f"{NAMESPACE}:claim:{claim_key(network, txid)}"
        stored = await self._client.set(key, invoice_id, nx=True)
        if stored:
            return None
        existing = await self._client.get(key)
        if existing is None or existing == invoice_id:
            return None
        return str(existing)

    async def owner_of_txid(self, network: str, txid: str) -> str | None:
        value = await self._client.get(f"{NAMESPACE}:claim:{claim_key(network, txid)}")
        return str(value) if value is not None else None

    async def remember_result(self, invoice_id: str, network: str, txid: str, payload: dict[str, Any], ttl_seconds: int) -> None:
        key = f"{NAMESPACE}:result:{cache_key(invoice_id, network, txid)}"
        await self._client.set(key, json.dumps(payload), ex=max(1, ttl_seconds))

    async def recall_result(self, invoice_id: str, network: str, txid: str) -> dict[str, Any] | None:
        value = await self._client.get(f"{NAMESPACE}:result:{cache_key(invoice_id, network, txid)}")
        return json.loads(value) if value else None

    async def remember_invoice_tip(self, invoice_id: str, network: str, height: int) -> None:
        await self._client.set(f"{NAMESPACE}:tip:{invoice_id}:{network}", int(height), nx=True)

    async def recall_invoice_tip(self, invoice_id: str, network: str) -> int | None:
        value = await self._client.get(f"{NAMESPACE}:tip:{invoice_id}:{network}")
        return int(value) if value is not None else None

    async def remember_invoice_quote(self, invoice_id: str, network: str, payload: dict[str, Any]) -> None:
        await self._client.set(f"{NAMESPACE}:quote:{invoice_id}:{network}", json.dumps(payload), nx=True)

    async def recall_invoice_quote(self, invoice_id: str, network: str) -> dict[str, Any] | None:
        value = await self._client.get(f"{NAMESPACE}:quote:{invoice_id}:{network}")
        return json.loads(value) if value else None

    async def remember_invoice_payment(self, invoice_id: str, network: str, txid: str, amount: str) -> None:
        await self._client.hsetnx(f"{NAMESPACE}:payments:{invoice_id}:{network}", txid, amount)

    async def recall_invoice_payments(self, invoice_id: str, network: str) -> list[tuple[str, str]]:
        entries = await self._client.hgetall(f"{NAMESPACE}:payments:{invoice_id}:{network}")
        return [(str(txid), str(amount)) for txid, amount in (entries or {}).items()]

    async def close(self) -> None:
        close_call = getattr(self._client, "aclose", None) or getattr(self._client, "close", None)
        if close_call is not None:
            await close_call()
