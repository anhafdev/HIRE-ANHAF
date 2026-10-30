from __future__ import annotations

from ..config import Config
from ..models import Network
from .base import BaseProvider
from .bitcoin import BlockchainInfoProvider, EsploraProvider
from .bsc import BscRpcProvider
from .ethereum import Erc20RpcProvider, EthereumRpcProvider
from .http_client import HttpSession
from .tron import TronNodeProvider, TronscanProvider


def build_bitcoin_chain(session: HttpSession, config: Config) -> list[BaseProvider]:
    chain: list[BaseProvider] = [EsploraProvider(session, config, url) for url in config.esplora_endpoints()]
    chain.append(BlockchainInfoProvider(session, config))
    return chain


def build_tron_chain(session: HttpSession, config: Config) -> list[BaseProvider]:
    chain: list[BaseProvider] = [
        TronNodeProvider(session, config, url, key) for url, key in config.tron_endpoints()
    ]
    chain.append(TronscanProvider(session, config))
    return chain


def build_bsc_chain(session: HttpSession, config: Config) -> list[BaseProvider]:
    return [BscRpcProvider(session, config, url) for url in config.bsc_endpoints()]


def build_ethereum_chain(session: HttpSession, config: Config) -> list[BaseProvider]:
    return [EthereumRpcProvider(session, config, url) for url in config.eth_endpoints()]


def build_erc20_chain(session: HttpSession, config: Config) -> list[BaseProvider]:
    return [Erc20RpcProvider(session, config, url) for url in config.eth_endpoints()]


def build_all_chains(session: HttpSession, config: Config) -> dict[Network, list[BaseProvider]]:
    return {
        Network.BTC: build_bitcoin_chain(session, config),
        Network.USDT_TRC20: build_tron_chain(session, config),
        Network.USDT_BEP20: build_bsc_chain(session, config),
        Network.ETH: build_ethereum_chain(session, config),
        Network.USDT_ERC20: build_erc20_chain(session, config),
    }


__all__ = [
    "BaseProvider",
    "BlockchainInfoProvider",
    "BscRpcProvider",
    "Erc20RpcProvider",
    "EsploraProvider",
    "EthereumRpcProvider",
    "HttpSession",
    "TronNodeProvider",
    "TronscanProvider",
    "build_all_chains",
    "build_bitcoin_chain",
    "build_bsc_chain",
    "build_erc20_chain",
    "build_ethereum_chain",
    "build_tron_chain",
]
