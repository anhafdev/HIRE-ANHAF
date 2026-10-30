from __future__ import annotations

from typing import Any

from ..config import Config
from ..models import ChainTransaction, Network, TokenTransfer
from ..networks.addresses import normalize_evm_address, same_address
from ..networks.decoding import read_evm_transfer_logs, read_hex_int, scale_units
from .evm_rpc import BaseEvmRpcProvider, EvmTokenRpcProvider
from .http_client import HttpSession
from .schemas import EvmTraceEntry, EvmTransaction, parse_or_fail


class Erc20RpcProvider(EvmTokenRpcProvider):
    decimals = 6

    def __init__(self, session: HttpSession, config: Config, rpc_url: str, label: str | None = None) -> None:
        super().__init__(session, config, rpc_url, Network.USDT_ERC20, "erc20", label)


class EthereumRpcProvider(BaseEvmRpcProvider):
    decimals = 18

    def __init__(self, session: HttpSession, config: Config, rpc_url: str, label: str | None = None) -> None:
        super().__init__(session, config, rpc_url, Network.ETH, "eth", label)

    def native_transfer(self, parsed_tx: EvmTransaction) -> list[TokenTransfer]:
        raw_value = read_hex_int(parsed_tx.value, 0)
        if not parsed_tx.to or raw_value <= 0:
            return []
        recipient = normalize_evm_address(parsed_tx.to)
        return [TokenTransfer(recipient=recipient, amount=scale_units(raw_value, self.decimals), contract=None)]

    def pending_transfers(self, parsed_tx: EvmTransaction) -> list[TokenTransfer]:
        return self.native_transfer(parsed_tx)

    def settled_transfers(self, parsed_tx: EvmTransaction, logs: list[dict[str, Any]]) -> list[TokenTransfer]:
        return self.native_transfer(parsed_tx)

    async def after_settled(
        self, transaction: ChainTransaction, parsed_tx: EvmTransaction, logs: list[dict[str, Any]]
    ) -> ChainTransaction:
        if not transaction.succeeded or not self.hides_the_eth_movement(transaction, logs):
            return transaction
        traced = await self.read_internal_payments(transaction.txid)
        if traced is None:
            transaction.raw["native_transfer_unreadable"] = True
        else:
            transaction.transfers = transaction.transfers + traced
        return transaction

    def hides_the_eth_movement(self, transaction: ChainTransaction, logs: list[dict[str, Any]]) -> bool:
        our_address = self.config.address_for(Network.ETH)
        if any(same_address(item.recipient, our_address) for item in transaction.transfers):
            return False
        if any(same_address(item.recipient, our_address) for item in read_evm_transfer_logs(logs, self.decimals)):
            return False
        calldata = (transaction.raw.get("tx") or {}).get("input") or "0x"
        return len(str(calldata)) > 2 or bool(logs)

    async def read_internal_payments(self, txid: str) -> list[TokenTransfer] | None:
        trace_url = self.config.eth_trace_rpc_url.strip().rstrip("/")
        if not trace_url:
            return None
        our_address = self.config.address_for(Network.ETH)
        try:
            body = {"jsonrpc": "2.0", "id": 1, "method": "trace_transaction", "params": [txid]}
            payload = await self.session.send_json(f"{self.name}:trace", trace_url, body)
            entries = (payload or {}).get("result") or []
            collected: list[TokenTransfer] = []
            for entry in entries:
                parsed = parse_or_fail(EvmTraceEntry, entry, self.name)
                if (parsed.type or "").lower() != "call" or (parsed.action.callType or "").lower() != "call":
                    continue
                raw_value = read_hex_int(parsed.action.value, 0)
                if raw_value <= 0 or not parsed.action.to or not same_address(parsed.action.to, our_address):
                    continue
                collected.append(
                    TokenTransfer(
                        recipient=normalize_evm_address(parsed.action.to),
                        amount=scale_units(raw_value, self.decimals),
                        contract=None,
                    )
                )
            return collected
        except Exception:
            return None
