from __future__ import annotations

import logging
from typing import Any

from ..config import Config
from ..models import ChainTransaction, Network
from ..resilience.circuit import CircuitBreaker
from ..resilience.guards import shielded
from .http_client import HttpSession

logger = logging.getLogger("cryptoverify.providers")


class BaseProvider:
    name = "provider"

    def __init__(self, session: HttpSession, config: Config, network: Network) -> None:
        self.session = session
        self.config = config
        self.network = network
        self.timeout_seconds = config.timeout_seconds
        self.retry_attempts = config.retry_attempts
        self.breaker = CircuitBreaker(config.breaker_failure_threshold, config.breaker_cooldown_seconds)

    def is_usable(self) -> bool:
        return True

    async def read_transaction(self, txid: str) -> ChainTransaction:
        raise NotImplementedError

    async def read_tip_height(self) -> int:
        raise NotImplementedError

    @shielded
    async def load_transaction(self, txid: str) -> ChainTransaction:
        return await self.read_transaction(txid)

    @shielded
    async def load_tip_height(self) -> int:
        return await self.read_tip_height()

    def blank_transaction(self, txid: str, raw: dict[str, Any] | None = None) -> ChainTransaction:
        return ChainTransaction(txid=txid, network=self.network, found=False, reported_by=self.name, raw=raw or {})

    @staticmethod
    def confirmations_between(tip_height: int | None, block_height: int | None) -> int:
        if block_height is None:
            return 0
        if tip_height is None:
            return 1
        return max(0, tip_height - block_height + 1)
