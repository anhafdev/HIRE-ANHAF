from __future__ import annotations

from typing import Any

from .config import Config
from .exceptions import NoProviderAnswered
from .models import ChainTransaction, Network, ProviderError
from .providers import HttpSession, build_all_chains
from .resilience import ask_two_and_compare, ask_until_one_answers, collect_health, rotate, usable_only

ROUND_ROBIN_NETWORKS = (Network.USDT_BEP20, Network.ETH, Network.USDT_ERC20)

EVM_CHAIN_NAMES = {
    Network.USDT_BEP20: "BSC",
    Network.ETH: "Ethereum",
    Network.USDT_ERC20: "Ethereum",
}


class ChainReader:
    def __init__(self, session: HttpSession, config: Config) -> None:
        self.config = config
        self.chains = build_all_chains(session, config)
        self._rotation: dict[Network, int] = {item: 0 for item in Network}

    def providers_for(self, network: Network) -> list[Any]:
        providers = usable_only(self.chains[network])
        if network in ROUND_ROBIN_NETWORKS and providers:
            self._rotation[network] = (self._rotation[network] + 1) % len(providers)
            return rotate(providers, self._rotation[network])
        return providers

    async def read_transaction(self, network: Network, txid: str) -> tuple[ChainTransaction, Any, list[ProviderError]]:
        async def ask(provider: Any) -> ChainTransaction:
            return await provider.load_transaction(txid)

        providers = self.providers_for(network)
        if self.config.cross_check_providers:
            return await ask_two_and_compare(providers, ask, lambda tx: tx.money_fingerprint())
        return await ask_until_one_answers(providers, ask)

    async def read_tip_height(self, network: Network) -> int | None:
        async def ask(provider: Any) -> int:
            return await provider.load_tip_height()

        try:
            height, _, _ = await ask_until_one_answers(self.providers_for(network), ask)
        except NoProviderAnswered:
            return None
        return int(height) if height else None

    async def find_hash_on_other_chains(self, requested: Network, txid: str) -> Network | None:
        home_chain = EVM_CHAIN_NAMES.get(requested)
        if home_chain is None:
            return None
        probed: set[str] = set()
        for network, chain_name in EVM_CHAIN_NAMES.items():
            if chain_name == home_chain or chain_name in probed:
                continue
            probed.add(chain_name)
            try:
                transaction, _, _ = await self.read_transaction(network, txid)
            except Exception:
                continue
            if transaction.found:
                return network
        return None

    async def report_health(self) -> dict[str, dict[str, str]]:
        report: dict[str, dict[str, str]] = {}
        for network in Network:
            if not self.config.is_enabled(network):
                report[network.value] = {"status": "disabled_no_address"}
                continue
            report[network.value] = await collect_health(usable_only(self.chains[network]))
        return report
