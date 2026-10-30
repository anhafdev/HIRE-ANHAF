from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from ..config import TRONSCAN_URL
from ..models import ChainTransaction, Network, right_now
from ..networks.decoding import read_pending_tron_transfer, read_tron_transfer_logs, read_tronscan_transfers
from .base import BaseProvider
from .schemas import TronscanTransaction, TronTransaction, TronTransactionInfo, parse_or_fail

TRON_DECIMALS = 6
SUCCESS_MARKERS = {"SUCCESS", "", None}


def moment_from_millis(millis: int | None) -> datetime | None:
    if not millis:
        return None
    return datetime.fromtimestamp(int(millis) / 1000, tz=timezone.utc)


class TronNodeProvider(BaseProvider):
    def __init__(self, session, config, base_url: str, api_key: str = "", label: str | None = None) -> None:
        super().__init__(session, config, Network.USDT_TRC20)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.name = label or f"tron:{self.base_url.split('//')[-1]}"

    def request_headers(self) -> dict[str, str]:
        return {"TRON-PRO-API-KEY": self.api_key} if self.api_key else {}

    async def read_tip_height(self) -> int:
        payload = await self.session.send_json(self.name, f"{self.base_url}/wallet/getnowblock", {}, self.request_headers())
        header = ((payload or {}).get("block_header") or {}).get("raw_data") or {}
        return int(header.get("number") or 0)

    async def read_transaction(self, txid: str) -> ChainTransaction:
        info_payload, tx_payload, tip_height = await asyncio.gather(
            self.session.send_json(self.name, f"{self.base_url}/wallet/gettransactioninfobyid", {"value": txid}, self.request_headers()),
            self.session.send_json(self.name, f"{self.base_url}/wallet/gettransactionbyid", {"value": txid}, self.request_headers()),
            self._tip_or_none(),
        )
        info = parse_or_fail(TronTransactionInfo, info_payload or {}, self.name)
        pending = parse_or_fail(TronTransaction, tx_payload or {}, self.name)
        if not info.blockNumber and not pending.txID:
            return self.blank_transaction(txid)
        outcome = (pending.ret[0].contractRet if pending.ret else None) or info.receipt.result
        settled = info.blockNumber is not None
        block_time = moment_from_millis(info.blockTimeStamp)
        moves = read_tron_transfer_logs([item.model_dump() for item in info.log], TRON_DECIMALS)
        if not moves and pending.raw_data.contract:
            call = pending.raw_data.contract[0].parameter.value
            moves = read_pending_tron_transfer(call.contract_address, call.data, TRON_DECIMALS)
        return ChainTransaction(
            txid=txid,
            network=Network.USDT_TRC20,
            found=True,
            succeeded=outcome in SUCCESS_MARKERS or outcome == "SUCCESS",
            settled_in_block=settled,
            confirmations=self.confirmations_between(tip_height, info.blockNumber) if settled else 0,
            block_height=info.blockNumber,
            block_time=block_time,
            first_seen_at=block_time or moment_from_millis(pending.raw_data.timestamp) or right_now(),
            transfers=moves,
            tip_height=tip_height,
            reported_by=self.name,
            raw={"info": info_payload or {}, "tx": tx_payload or {}},
        )

    async def _tip_or_none(self) -> int | None:
        try:
            return await self.read_tip_height()
        except Exception:
            return None


class TronscanProvider(BaseProvider):
    name = "tronscan"

    def __init__(self, session, config) -> None:
        super().__init__(session, config, Network.USDT_TRC20)
        self.base_url = TRONSCAN_URL

    async def read_tip_height(self) -> int:
        payload = await self.session.fetch_json(self.name, f"{self.base_url}/api/block", {"sort": "-number", "limit": 1})
        blocks = (payload or {}).get("data") or []
        return int(blocks[0].get("number", 0)) if blocks else 0

    async def read_transaction(self, txid: str) -> ChainTransaction:
        tx_payload, tip_height = await asyncio.gather(
            self.session.fetch_json(self.name, f"{self.base_url}/api/transaction-info", {"hash": txid}, allow_missing=True),
            self._tip_or_none(),
        )
        if not tx_payload or not (tx_payload.get("hash") or tx_payload.get("block")):
            return self.blank_transaction(txid)
        parsed = parse_or_fail(TronscanTransaction, tx_payload, self.name)
        entries = [item.model_dump() for item in parsed.trc20TransferInfo]
        if not entries and parsed.tokenTransferInfo is not None:
            entries = [parsed.tokenTransferInfo.model_dump()]
        settled = bool(parsed.block)
        block_time = moment_from_millis(parsed.timestamp)
        return ChainTransaction(
            txid=txid,
            network=Network.USDT_TRC20,
            found=True,
            succeeded=(parsed.contractRet or "SUCCESS") == "SUCCESS",
            settled_in_block=settled,
            confirmations=self.confirmations_between(tip_height, parsed.block) if settled else 0,
            block_height=parsed.block,
            block_time=block_time,
            first_seen_at=block_time or right_now(),
            transfers=read_tronscan_transfers(entries),
            tip_height=tip_height,
            reported_by=self.name,
            raw=tx_payload,
        )

    async def _tip_or_none(self) -> int | None:
        try:
            return await self.read_tip_height()
        except Exception:
            return None
