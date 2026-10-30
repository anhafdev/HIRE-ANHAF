from __future__ import annotations

import asyncio
import itertools
from datetime import datetime, timezone
from typing import Any

from ..config import Config
from ..exceptions import ProviderCallFailed
from ..models import ChainTransaction, Network, TokenTransfer, right_now
from ..networks.decoding import read_evm_transfer_logs, read_hex_int, read_pending_evm_transfer
from .base import BaseProvider
from .http_client import HttpSession
from .schemas import EvmBlock, EvmReceipt, EvmTransaction, parse_or_fail

SUCCESS_STATUS = {"0x1", "0x01", 1}


class BaseEvmRpcProvider(BaseProvider):
    decimals = 18

    def __init__(
        self,
        session: HttpSession,
        config: Config,
        rpc_url: str,
        network: Network,
        name_prefix: str,
        label: str | None = None,
    ) -> None:
        super().__init__(session, config, network)
        self.rpc_url = rpc_url.rstrip("/")
        self.name = label or f"{name_prefix}:{self.rpc_url.split('//')[-1]}"
        self._call_counter = itertools.count(1)

    async def call_rpc(self, method: str, params: list[Any], allow_missing: bool = False) -> Any:
        body = {"jsonrpc": "2.0", "id": next(self._call_counter), "method": method, "params": params}
        payload = await self.session.send_json(self.name, self.rpc_url, body, allow_missing=allow_missing)
        if payload is None:
            return None
        if isinstance(payload, dict) and payload.get("error"):
            detail = payload["error"].get("message", "rpc error")
            raise ProviderCallFailed(self.name, f"rpc rejected {method}: {detail}", retryable=False)
        return (payload or {}).get("result")

    async def read_tip_height(self) -> int:
        return read_hex_int(await self.call_rpc("eth_blockNumber", []))

    def pending_transfers(self, parsed_tx: EvmTransaction) -> list[TokenTransfer]:
        raise NotImplementedError

    def settled_transfers(self, parsed_tx: EvmTransaction, logs: list[dict[str, Any]]) -> list[TokenTransfer]:
        raise NotImplementedError

    async def after_settled(
        self, transaction: ChainTransaction, parsed_tx: EvmTransaction, logs: list[dict[str, Any]]
    ) -> ChainTransaction:
        return transaction

    async def read_transaction(self, txid: str) -> ChainTransaction:
        (tx_result, block_time), receipt_result, tip_height = await asyncio.gather(
            self._transaction_with_block_time(txid),
            self.call_rpc("eth_getTransactionReceipt", [txid], allow_missing=True),
            self._tip_or_none(),
        )
        if not tx_result:
            return self.blank_transaction(txid)
        parsed_tx = parse_or_fail(EvmTransaction, tx_result, self.name)
        if not receipt_result or parsed_tx.blockNumber is None:
            return ChainTransaction(
                txid=txid,
                network=self.network,
                found=True,
                succeeded=True,
                settled_in_block=False,
                confirmations=0,
                first_seen_at=right_now(),
                transfers=self.pending_transfers(parsed_tx),
                contracts_touched=[parsed_tx.to] if parsed_tx.to else [],
                tip_height=tip_height,
                reported_by=self.name,
                raw={"tx": tx_result, "receipt": None},
            )
        parsed_receipt = parse_or_fail(EvmReceipt, receipt_result, self.name)
        block_height = read_hex_int(parsed_receipt.blockNumber or parsed_tx.blockNumber, 0) or None
        logs = [item.model_dump() for item in parsed_receipt.logs]
        transaction = ChainTransaction(
            txid=txid,
            network=self.network,
            found=True,
            succeeded=(parsed_receipt.status in SUCCESS_STATUS) if parsed_receipt.status is not None else True,
            settled_in_block=block_height is not None,
            confirmations=self.confirmations_between(tip_height, block_height),
            block_height=block_height,
            block_time=block_time,
            first_seen_at=right_now(),
            transfers=self.settled_transfers(parsed_tx, logs),
            contracts_touched=[str(item.get("address")) for item in logs if item.get("address")],
            tip_height=tip_height,
            reported_by=self.name,
            raw={"tx": tx_result, "receipt": receipt_result},
        )
        return await self.after_settled(transaction, parsed_tx, logs)

    async def _transaction_with_block_time(self, txid: str) -> tuple[Any, datetime | None]:
        tx_result = await self.call_rpc("eth_getTransactionByHash", [txid], allow_missing=True)
        block_number = tx_result.get("blockNumber") if isinstance(tx_result, dict) else None
        if not block_number:
            return tx_result, None
        return tx_result, await self._block_time_or_none(block_number)

    async def _block_time_or_none(self, block_number: str) -> datetime | None:
        try:
            block_result = await self.call_rpc("eth_getBlockByNumber", [block_number, False], allow_missing=True)
            if not block_result:
                return None
            stamp = read_hex_int(parse_or_fail(EvmBlock, block_result, self.name).timestamp, 0)
            return datetime.fromtimestamp(stamp, timezone.utc) if stamp else None
        except Exception:
            return None

    async def _tip_or_none(self) -> int | None:
        try:
            return await self.read_tip_height()
        except Exception:
            return None


class EvmTokenRpcProvider(BaseEvmRpcProvider):
    def pending_transfers(self, parsed_tx: EvmTransaction) -> list[TokenTransfer]:
        return read_pending_evm_transfer(parsed_tx.to, parsed_tx.input, self.decimals)

    def settled_transfers(self, parsed_tx: EvmTransaction, logs: list[dict[str, Any]]) -> list[TokenTransfer]:
        return read_evm_transfer_logs(logs, self.decimals)
