from __future__ import annotations

from ..config import Config
from ..models import Network
from .evm_rpc import EvmTokenRpcProvider
from .http_client import HttpSession


class BscRpcProvider(EvmTokenRpcProvider):
    decimals = 18

    def __init__(self, session: HttpSession, config: Config, rpc_url: str, label: str | None = None) -> None:
        super().__init__(session, config, rpc_url, Network.USDT_BEP20, "bsc", label)
