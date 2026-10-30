from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable

from .assessment import build_result, judge_payment
from .chain_reader import ChainReader
from .codes import Code
from .config import Config
from .exceptions import NoProviderAnswered, ProvidersDisagree
from .cross_chain import hash_on_other_chain_result, unreadable_native_result
from .guardrails import already_used_result, inspect_request, internal_error_result
from .models import Network, Tier, VerifyResult, VerifyStatus, result_from_dict
from .pricing import quote_from_payload
from .providers import HttpSession
from .resolve import HashIdentity, identify_hash
from .storage import StorageBackend, build_storage
from .sync_bridge import BackgroundLoop
from .watcher import follow_until_final

logger = logging.getLogger("cryptoverify")

CACHEABLE_STATUSES = {VerifyStatus.CONFIRMED, VerifyStatus.UNDERPAID, VerifyStatus.FAILED_TX, VerifyStatus.STALE}


class DepositVerifier:
    def __init__(
        self,
        config: Config | None = None,
        storage: StorageBackend | None = None,
        session: HttpSession | None = None,
    ) -> None:
        self.config = config or Config()
        self.storage = storage or build_storage(self.config.storage_url)
        self.session = session or HttpSession(self.config.timeout_seconds)
        self.reader = ChainReader(self.session, self.config)
        self._storage_ready = False
        self._sync_loop = BackgroundLoop()
        logging.getLogger("cryptoverify").setLevel(self.config.log_level.upper())

    async def open_invoice(self, invoice_id: str, network: Network) -> int | None:
        try:
            await self._ready_storage()
            height = await self.reader.read_tip_height(network)
            if height is not None:
                await self.storage.remember_invoice_tip(invoice_id, network.value, height)
            return height
        except Exception:
            logger.exception("could not record the chain tip for %s", invoice_id)
            return None

    async def identify(self, txid: str) -> HashIdentity:
        try:
            return await identify_hash(self.reader, self.config, txid)
        except Exception:
            logger.exception("could not identify %s", txid)
            return HashIdentity(txid=str(txid or ""))

    async def verify(
        self,
        txid: str,
        network: Network,
        expected_amount: Decimal,
        invoice_id: str,
        invoice_created_at: datetime | None = None,
    ) -> VerifyResult:
        try:
            return await self._run_verification(txid, network, expected_amount, invoice_id, invoice_created_at)
        except Exception:
            logger.exception("unexpected failure while verifying %s on %s", txid, network)
            return internal_error_result(network, txid, invoice_id)

    async def _run_verification(
        self,
        txid: str,
        network: Network,
        expected_amount: Decimal,
        invoice_id: str,
        invoice_created_at: datetime | None = None,
    ) -> VerifyResult:
        checked, refusal = inspect_request(self.config, txid, network, expected_amount, invoice_id)
        if refusal is not None:
            return refusal
        clean_txid, amount = checked

        await self._ready_storage()
        cached = await self.storage.recall_result(invoice_id, network.value, clean_txid)
        if cached is not None:
            return result_from_dict(cached)

        owner = await self.storage.owner_of_txid(network.value, clean_txid)
        if owner is not None and owner != invoice_id:
            return already_used_result(network, clean_txid, invoice_id, owner, amount)

        try:
            transaction, provider, failures = await self.reader.read_transaction(network, clean_txid)
        except ProvidersDisagree as clash:
            logger.error("provider disagreement on %s %s: %s", network.value, clean_txid, clash.detail)
            return build_result(
                VerifyStatus.PROVIDER_UNAVAILABLE, Code.PROVIDERS_DISAGREE,
                "We could not confirm this payment safely right now. Please try again shortly.",
                network=network, invoice_id=invoice_id, txid=clean_txid, expected_amount=amount,
            )
        except NoProviderAnswered as outage:
            logger.warning("all providers failed for %s %s", network.value, clean_txid)
            return build_result(
                VerifyStatus.PROVIDER_UNAVAILABLE, Code.EVERY_PROVIDER_FAILED,
                "Blockchain lookup is temporarily unavailable. Please try again in a minute.",
                network=network, invoice_id=invoice_id, txid=clean_txid, expected_amount=amount,
                provider_errors=outage.failures,
            )

        blocked = unreadable_native_result(network, transaction, invoice_id, amount)
        if blocked is not None:
            return blocked

        invoice_tip = await self.storage.recall_invoice_tip(invoice_id, network.value)
        locked_quote = quote_from_payload(await self.storage.recall_invoice_quote(invoice_id, network.value))
        result = judge_payment(transaction, self.config, network, amount, invoice_created_at, invoice_tip, locked_quote)
        if result.status is VerifyStatus.NOT_FOUND:
            rerouted = await hash_on_other_chain_result(self.reader, self.config, network, clean_txid, invoice_id, amount)
            if rerouted is not None:
                return rerouted
        result.invoice_id = invoice_id
        result.provider_used = provider.name
        result.provider_errors = failures

        if result.status is VerifyStatus.CONFIRMED:
            conflict = await self.storage.claim_txid(network.value, clean_txid, invoice_id)
            if conflict is not None:
                return already_used_result(network, clean_txid, invoice_id, conflict, amount)

        if result.status is VerifyStatus.UNDERPAID and self.config.allow_partial_payments:
            return result
        if result.status in CACHEABLE_STATUSES:
            await self.storage.remember_result(
                invoice_id, network.value, clean_txid, result.to_dict(), self.config.result_cache_ttl_seconds
            )
        return result

    def verify_sync(
        self,
        txid: str,
        network: Network,
        expected_amount: Decimal,
        invoice_id: str,
        invoice_created_at: datetime | None = None,
    ) -> VerifyResult:
        try:
            return self._sync_loop.run(
                self.verify(
                    txid=txid, network=network, expected_amount=expected_amount,
                    invoice_id=invoice_id, invoice_created_at=invoice_created_at,
                )
            )
        except Exception:
            logger.exception("sync bridge failed for %s on %s", txid, network)
            return internal_error_result(network, txid, invoice_id)

    async def watch(
        self, txid: str, network: Network, expected_amount: Decimal, invoice_id: str,
        invoice_created_at: datetime | None = None, on_update: Callable[[VerifyResult], Any] | None = None,
        stop_after_seconds: float = 1800.0, settle_at: Tier = Tier.CONFIRMED,
    ) -> VerifyResult:
        return await follow_until_final(
            self, txid, network, expected_amount, invoice_id,
            invoice_created_at, on_update, stop_after_seconds, settle_at,
        )

    async def health(self) -> dict[str, dict[str, str]]:
        try:
            return await self.reader.report_health()
        except Exception:
            logger.exception("health check failed")
            return {item.value: {"status": "unknown"} for item in Network}

    async def close(self) -> None:
        for shutdown in (self.session.close, self.storage.close):
            try:
                await shutdown()
            except Exception:
                logger.debug("cleanup step failed", exc_info=True)
        self._sync_loop.shutdown()

    async def __aenter__(self) -> "DepositVerifier":
        await self._ready_storage()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def _ready_storage(self) -> None:
        if not self._storage_ready:
            await self.storage.prepare()
            self._storage_ready = True
