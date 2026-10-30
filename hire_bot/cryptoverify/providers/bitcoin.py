from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from ..config import BLOCKCHAIN_INFO_URL
from ..models import ChainTransaction, Network, right_now
from ..networks.decoding import read_bitcoin_outputs, signals_replace_by_fee
from .base import BaseProvider
from .schemas import BlockchainInfoTransaction, EsploraTransaction, parse_or_fail

BITCOIN_DECIMALS = 8


def moment_from_epoch(seconds: int | None) -> datetime | None:
    if not seconds:
        return None
    return datetime.fromtimestamp(int(seconds), tz=timezone.utc)


class EsploraProvider(BaseProvider):
    def __init__(self, session, config, base_url: str, label: str | None = None) -> None:
        super().__init__(session, config, Network.BTC)
        self.base_url = base_url.rstrip("/")
        self.name = label or f"esplora:{self.base_url.split('//')[-1]}"

    async def read_tip_height(self) -> int:
        payload = await self.session.fetch_json(self.name, f"{self.base_url}/api/blocks/tip/height")
        return int(payload)

    async def read_transaction(self, txid: str) -> ChainTransaction:
        tx_payload, tip_height = await asyncio.gather(
            self.session.fetch_json(self.name, f"{self.base_url}/api/tx/{txid}", allow_missing=True),
            self._tip_or_none(),
        )
        if tx_payload is None:
            return self.blank_transaction(txid)
        parsed = parse_or_fail(EsploraTransaction, tx_payload, self.name)
        settled = bool(parsed.status.confirmed)
        block_time = moment_from_epoch(parsed.status.block_time)
        return ChainTransaction(
            txid=txid,
            network=Network.BTC,
            found=True,
            succeeded=True,
            settled_in_block=settled,
            confirmations=self.confirmations_between(tip_height, parsed.status.block_height) if settled else 0,
            block_height=parsed.status.block_height if settled else None,
            block_time=block_time,
            first_seen_at=block_time or right_now(),
            replaceable=signals_replace_by_fee([item.model_dump() for item in parsed.vin]),
            transfers=read_bitcoin_outputs([item.model_dump() for item in parsed.vout], BITCOIN_DECIMALS),
            tip_height=tip_height,
            reported_by=self.name,
            raw=tx_payload if isinstance(tx_payload, dict) else {"payload": tx_payload},
        )

    async def _tip_or_none(self) -> int | None:
        try:
            return await self.read_tip_height()
        except Exception:
            return None


class BlockchainInfoProvider(BaseProvider):
    name = "blockchain.info"

    def __init__(self, session, config) -> None:
        super().__init__(session, config, Network.BTC)
        self.base_url = BLOCKCHAIN_INFO_URL

    async def read_tip_height(self) -> int:
        payload = await self.session.fetch_json(self.name, f"{self.base_url}/latestblock")
        return int((payload or {}).get("height", 0))

    async def read_transaction(self, txid: str) -> ChainTransaction:
        tx_payload, tip_height = await asyncio.gather(
            self.session.fetch_json(self.name, f"{self.base_url}/rawtx/{txid}", allow_missing=True),
            self._tip_or_none(),
        )
        if not tx_payload:
            return self.blank_transaction(txid)
        parsed = parse_or_fail(BlockchainInfoTransaction, tx_payload, self.name)
        settled = parsed.block_height is not None
        block_time = moment_from_epoch(parsed.time)
        return ChainTransaction(
            txid=txid,
            network=Network.BTC,
            found=True,
            succeeded=True,
            settled_in_block=settled,
            confirmations=self.confirmations_between(tip_height, parsed.block_height) if settled else 0,
            block_height=parsed.block_height,
            block_time=block_time if settled else None,
            first_seen_at=block_time or right_now(),
            replaceable=signals_replace_by_fee([item.model_dump() for item in parsed.inputs]),
            transfers=read_bitcoin_outputs([item.model_dump() for item in parsed.out], BITCOIN_DECIMALS),
            tip_height=tip_height,
            reported_by=self.name,
            raw=tx_payload if isinstance(tx_payload, dict) else {"payload": tx_payload},
        )

    async def _tip_or_none(self) -> int | None:
        try:
            return await self.read_tip_height()
        except Exception:
            return None
