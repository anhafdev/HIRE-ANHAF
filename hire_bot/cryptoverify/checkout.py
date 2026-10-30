from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from .amounts import read_amount, smallest_acceptable_amount
from .any_asset import lock_all_rates, route_submission
from .checkout_models import (
    INVOICE_ALPHABET,
    NETWORK_LABELS,
    NETWORK_UNITS,
    CheckoutStep,
    PaymentRequest,
    StepOutcome,
    new_invoice_id,
    usd_text,
)
from .codes import Code
from .models import TOKEN_CONTRACT_BY_NETWORK, Network, VerifyResult, VerifyStatus, right_now
from .partial_payments import refresh_totals, settle_after_check
from .pricing import PriceQuote, fetch_usd_price, required_coin_for


class CheckoutSession:
    def __init__(self, verifier, invoice_id: str | None = None, expiry_minutes: int = 30) -> None:
        self.verifier = verifier
        self.config = verifier.config
        self.invoice_id = invoice_id or new_invoice_id()
        self.expiry_minutes = expiry_minutes
        self.step = CheckoutStep.PICK_NETWORK
        self.network: Network | None = None
        self.amount: Decimal | None = None
        self.usd_amount: Decimal | None = None
        self.quote: PriceQuote | None = None
        self.request: PaymentRequest | None = None
        self.result: VerifyResult | None = None
        self.attempts: list[VerifyResult] = []
        self.payments: list[tuple[str, Decimal]] = []
        self.amount_paid_total: Decimal = Decimal(0)
        self.amount_remaining: Decimal | None = None

    def available_networks(self) -> list[Network]:
        return self.config.enabled_networks()

    def menu(self) -> list[tuple[int, Network, str]]:
        return [(index, item, NETWORK_LABELS[item]) for index, item in enumerate(self.available_networks(), start=1)]

    def choose_network(self, picked: Network | str | int) -> StepOutcome:
        options = self.available_networks()
        if not options:
            return StepOutcome(False, CheckoutStep.PICK_NETWORK, "No deposit address is configured yet.")
        chosen = self._match_network(picked, options)
        if chosen is None:
            return StepOutcome(False, CheckoutStep.PICK_NETWORK, "That is not one of the listed payment methods.")
        self.network = chosen
        self.step = CheckoutStep.ENTER_AMOUNT
        return StepOutcome(True, CheckoutStep.ENTER_AMOUNT, f"Paying with {NETWORK_LABELS[chosen]}.")

    def set_amount(self, raw_value) -> StepOutcome:
        if self.network is None:
            return StepOutcome(False, CheckoutStep.PICK_NETWORK, "Pick a payment method first.")
        amount = read_amount(raw_value)
        if amount is None:
            return StepOutcome(False, CheckoutStep.ENTER_AMOUNT, "Enter a positive number, for example 50 or 0.01.")
        self.amount = amount
        self.step = CheckoutStep.SHOW_ADDRESS
        return StepOutcome(True, CheckoutStep.SHOW_ADDRESS, f"Amount set to {amount}.")

    async def set_usd_amount(self, raw_value) -> StepOutcome:
        if self.network is None:
            return StepOutcome(False, CheckoutStep.PICK_NETWORK, "Pick a payment method first.")
        usd = read_amount(raw_value)
        if usd is None:
            return StepOutcome(False, CheckoutStep.ENTER_AMOUNT, "Enter a positive USD amount, for example 1 or 49.99.")
        quote = await fetch_usd_price(self.verifier.session, self.config, self.network)
        if quote is None:
            return StepOutcome(
                False,
                CheckoutStep.ENTER_AMOUNT,
                "A rate could not be established right now. Please retry in a moment.",
                code=Code.PRICE_UNAVAILABLE,
            )
        self.usd_amount = usd
        self.quote = quote
        self.amount = required_coin_for(usd, quote, self.network, self.config)
        self.step = CheckoutStep.SHOW_ADDRESS
        unit = NETWORK_UNITS[self.network]
        thin = "  (thin quote, single source)" if quote.quote_is_thin else ""
        return StepOutcome(
            True, CheckoutStep.SHOW_ADDRESS, f"Rate locked: 1 {unit} = ${usd_text(quote.price)}  ({quote.source}){thin}"
        )

    async def open_payment(self) -> StepOutcome:
        if self.network is None or self.amount is None:
            return StepOutcome(False, self.step, "Pick a method and an amount first.")
        created_at = right_now()
        tip_height = await self.verifier.open_invoice(self.invoice_id, self.network)
        self.request = PaymentRequest(
            invoice_id=self.invoice_id,
            network=self.network,
            amount=self.amount,
            address=self.config.address_for(self.network),
            label=NETWORK_LABELS[self.network],
            unit=NETWORK_UNITS[self.network],
            created_at=created_at,
            expires_at=created_at + timedelta(minutes=self.expiry_minutes),
            minimum_accepted=smallest_acceptable_amount(self.amount, self.config, self.network),
            required_confirmations=self.config.min_confirmations_for(self.network),
            token_contract=TOKEN_CONTRACT_BY_NETWORK.get(self.network),
            tip_height=tip_height,
            usd_amount=self.usd_amount,
            locked_rate=self.quote.price if self.quote else None,
            rate_source=self.quote.source if self.quote else "",
            rate_quote_currency=self.quote.quote_currency if self.quote else "",
            quote_is_thin=self.quote.quote_is_thin if self.quote else False,
            shared_address_with=self.config.networks_sharing_address(self.network),
        )
        self.request.accepted, self.request.unavailable = await lock_all_rates(self)
        await refresh_totals(self)
        self.step = CheckoutStep.AWAIT_TXID
        return StepOutcome(True, CheckoutStep.AWAIT_TXID, "Send the payment, then submit the transaction hash.")

    async def submit_txid(self, txid: str) -> VerifyResult:
        return await self._check(txid, on_update=None, live=False)

    async def submit_txid_and_follow(self, txid: str, on_update=None) -> VerifyResult:
        return await self._check(txid, on_update=on_update, live=True)

    def watch_window_seconds(self) -> float:
        window = float(self.config.watch_timeout_minutes * 60)
        if self.request is not None:
            until_expiry = (self.request.expires_at - right_now()).total_seconds()
            window = min(window, max(1.0, until_expiry))
        return window

    async def reverify_for_amount(
        self, txid: str, amount: Decimal, on_update, live: bool, network: Network | None = None
    ) -> VerifyResult:
        shared = {
            "txid": txid,
            "network": network or self.request.network,
            "expected_amount": amount,
            "invoice_id": self.request.invoice_id,
            "invoice_created_at": self.request.created_at,
        }
        if live:
            return await self.verifier.watch(on_update=on_update, stop_after_seconds=self.watch_window_seconds(), **shared)
        return await self.verifier.verify(**shared)

    async def _check(self, txid: str, on_update, live: bool) -> VerifyResult:
        if self.request is None:
            outcome = await self.open_payment()
            if not outcome.ok or self.request is None:
                return self._refuse(outcome.message)
        if self.request.is_expired():
            return self._refuse("This invoice has expired. Start a new payment.")
        result = await route_submission(self, txid, on_update, live)
        if result is None:
            partials = self.config.allow_partial_payments
            expected = self.amount_remaining if partials and self.amount_remaining else self.request.amount
            result = await self.reverify_for_amount(txid, expected, on_update, live)
            if partials:
                result = await settle_after_check(self, txid, result, on_update, live)
        self.result = result
        self.attempts.append(result)
        if result.status is VerifyStatus.CONFIRMED:
            self.step = CheckoutStep.DONE
        return result

    def _refuse(self, message: str) -> VerifyResult:
        from .assessment import build_result

        return build_result(
            VerifyStatus.INVALID_INPUT,
            Code.MISSING_INVOICE_ID,
            message,
            network=self.network,
            invoice_id=self.invoice_id,
        )

    @staticmethod
    def _match_network(picked, options: list[Network]) -> Network | None:
        if isinstance(picked, Network):
            return picked if picked in options else None
        text = str(picked).strip().lower()
        if text.isdigit():
            position = int(text)
            return options[position - 1] if 1 <= position <= len(options) else None
        for item in options:
            if text in {item.value.lower(), NETWORK_LABELS[item].lower()}:
                return item
        aliases = {"btc": Network.BTC, "bitcoin": Network.BTC, "trc20": Network.USDT_TRC20, "tron": Network.USDT_TRC20,
                   "bep20": Network.USDT_BEP20, "bsc": Network.USDT_BEP20, "eth": Network.ETH, "ethereum": Network.ETH, "erc20": Network.USDT_ERC20}
        guess = aliases.get(text)
        return guess if guess in options else None
