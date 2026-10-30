from __future__ import annotations

from decimal import Decimal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .exceptions import ConfigurationError
from .models import Network
from .networks.addresses import (
    is_valid_bitcoin_address,
    is_valid_evm_address,
    is_valid_tron_address,
    normalize_evm_address,
)

PUBLIC_BSC_NODES = (
    "https://bsc-dataseed.bnbchain.org",
    "https://bsc-dataseed.defibit.io",
    "https://bsc-dataseed.ninicoin.io",
    "https://bsc-rpc.publicnode.com",
)
PUBLIC_ETH_NODES = (
    "https://ethereum.publicnode.com",
    "https://ethereum-rpc.publicnode.com",
    "https://eth.drpc.org",
    "https://ethereum.public.blockpi.network/v1/rpc/public",
    "https://eth.merkle.io",
    "https://eth.api.onfinality.io/public",
    "https://public.1rpc.io/eth",
    "https://eth-mainnet.g.alchemy.com/public",
)
PUBLIC_ESPLORA_NODES = ("https://mempool.space", "https://blockstream.info")
TRONGRID_URL = "https://api.trongrid.io"
TRONSCAN_URL = "https://apilist.tronscanapi.com"
BLOCKCHAIN_INFO_URL = "https://blockchain.info"


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CV_", env_file=".env", env_file_encoding="utf-8", extra="ignore")

    addr_btc: str = ""
    addr_trc20: str = ""
    addr_bep20: str = ""
    addr_eth: str = ""
    addr_erc20: str = ""

    trongrid_api_key: str = ""
    bsc_rpc_url: str = ""
    btc_esplora_url: str = ""
    tron_node_url: str = ""
    eth_rpc_url: str = ""
    eth_trace_rpc_url: str = ""

    min_conf_btc: int = 1
    min_conf_trc20: int = 1
    min_conf_bep20: int = 3
    min_conf_eth: int = 12
    min_conf_erc20: int = 12

    probe_other_chains: bool = True
    accept_any_configured_asset: bool = True
    allow_underpayment: bool = False
    allow_partial_payments: bool = True
    price_max_spread_percent: Decimal = Decimal("5")
    price_safety_percent: Decimal = Decimal("0")
    usdt_usd_rate: Decimal = Decimal("1.0")
    price_timeout_seconds: float = 6.0
    watch_timeout_minutes: int = 30
    brand_name: str = ""
    brand_tagline: str = ""
    brand_support: str = ""
    brand_website: str = ""
    brand_receipt_prefix: str = "RCP"
    receipt_dir: str = ""
    tolerance_percent: Decimal = Decimal("0.5")
    dust_allowance_usdt: Decimal = Decimal("0.01")
    dust_allowance_btc: Decimal = Decimal("0.00000100")
    dust_allowance_eth: Decimal = Decimal("0.00001")
    clock_skew_minutes: int = 10
    reorg_buffer_blocks: int = 6
    reject_rbf_on_detected: bool = True
    cross_check_providers: bool = False

    storage_url: str = "sqlite:///cryptoverify.db"
    result_cache_ttl_seconds: int = 86400
    timeout_seconds: float = 8.0
    retry_attempts: int = 2
    breaker_failure_threshold: int = 5
    breaker_cooldown_seconds: float = 60.0
    log_level: str = "INFO"

    @field_validator("addr_btc")
    @classmethod
    def _check_btc(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned and not is_valid_bitcoin_address(cleaned):
            raise ConfigurationError(f"CV_ADDR_BTC is not a valid Bitcoin address: {cleaned!r}")
        return cleaned

    @field_validator("addr_trc20")
    @classmethod
    def _check_tron(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned and not is_valid_tron_address(cleaned):
            raise ConfigurationError(f"CV_ADDR_TRC20 is not a valid TRON address: {cleaned!r}")
        return cleaned

    @field_validator("addr_bep20", "addr_eth", "addr_erc20")
    @classmethod
    def _check_evm(cls, value: str, info) -> str:
        cleaned = value.strip()
        if cleaned and not is_valid_evm_address(cleaned):
            raise ConfigurationError(f"CV_{info.field_name.upper()} failed EIP-55 validation: {cleaned!r}")
        return normalize_evm_address(cleaned) if cleaned else cleaned

    @classmethod
    def from_env(cls, env_file: str = ".env") -> "Config":
        return cls(_env_file=env_file)

    def address_for(self, network: Network) -> str:
        return {
            Network.BTC: self.addr_btc,
            Network.USDT_TRC20: self.addr_trc20,
            Network.USDT_BEP20: self.addr_bep20,
            Network.ETH: self.addr_eth,
            Network.USDT_ERC20: self.addr_erc20,
        }[network]

    def min_confirmations_for(self, network: Network) -> int:
        return {
            Network.BTC: self.min_conf_btc,
            Network.USDT_TRC20: self.min_conf_trc20,
            Network.USDT_BEP20: self.min_conf_bep20,
            Network.ETH: self.min_conf_eth,
            Network.USDT_ERC20: self.min_conf_erc20,
        }[network]

    def dust_allowance_for(self, network: Network) -> Decimal:
        if network is Network.BTC:
            return self.dust_allowance_btc
        if network is Network.ETH:
            return self.dust_allowance_eth
        return self.dust_allowance_usdt

    def is_enabled(self, network: Network) -> bool:
        return bool(self.address_for(network))

    def enabled_networks(self) -> list[Network]:
        return [item for item in Network if self.is_enabled(item)]

    def networks_sharing_address(self, network: Network) -> list[Network]:
        own = self.address_for(network)
        if not own:
            return []
        return [
            item
            for item in self.enabled_networks()
            if item is not network and self.address_for(item).lower() == own.lower()
        ]

    def esplora_endpoints(self) -> list[str]:
        custom = [self.btc_esplora_url.rstrip("/")] if self.btc_esplora_url else []
        return custom + list(PUBLIC_ESPLORA_NODES)

    def bsc_endpoints(self) -> list[str]:
        custom = [self.bsc_rpc_url.rstrip("/")] if self.bsc_rpc_url else []
        return custom + list(PUBLIC_BSC_NODES)

    def eth_endpoints(self) -> list[str]:
        custom = [self.eth_rpc_url.rstrip("/")] if self.eth_rpc_url else []
        return custom + list(PUBLIC_ETH_NODES)

    def tron_endpoints(self) -> list[tuple[str, str]]:
        custom = [(self.tron_node_url.rstrip("/"), "")] if self.tron_node_url else []
        return custom + [(TRONGRID_URL, self.trongrid_api_key)]
