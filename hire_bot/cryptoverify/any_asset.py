from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any

from .assessment import build_result
from .checkout_models import NETWORK_LABELS, NETWORK_UNITS, AcceptedOption, display_amount, usd_text
from .codes import Code
from .models import TOKEN_CONTRACT_BY_NETWORK, Network, VerifyResult, VerifyStatus
from .pricing import fetch_usd_price, quote_from_payload, required_coin_for, usd_value
from .resolve import AssetMovement


async def lock_all_rates(session: Any) -> tuple[list[AcceptedOption], list[Network]]:
    config = session.config
    selected = session.network

    def option_for(network: Network, required: Decimal) -> AcceptedOption:
        return AcceptedOption(
            network=network,
            label=NETWORK_LABELS[network],
            asset=NETWORK_UNITS[network],
            address=config.address_for(network),
            required_coin=required,
            token_contract=TOKEN_CONTRACT_BY_NETWORK.get(network),
        )

    if session.usd_amount is None or session.quote is None:
        return [option_for(selected, session.amount)], []

    async def price_one(network: Network) -> tuple[Network, AcceptedOption | None]:
        quote = session.quote if network is selected else await fetch_usd_price(session.verifier.session, config, network)
        if quote is None:
            return network, None
        required = session.amount if network is selected else required_coin_for(session.usd_amount, quote, network, config)
        payload = dict(quote.to_payload(), usd_amount=str(session.usd_amount), required_coin=str(required))
        await session.verifier.storage.remember_invoice_quote(session.invoice_id, network.value, payload)
        return network, option_for(network, required)

    outcomes = await asyncio.gather(*(price_one(network) for network in config.enabled_networks()))
    accepted = [option for _, option in outcomes if option is not None]
    unavailable = [network for network, option in outcomes if option is None]
    return accepted, unavailable


def name_the_asset(movement: AssetMovement) -> str:
    native = "" if TOKEN_CONTRACT_BY_NETWORK.get(movement.network) else "native "
    return f"{display_amount(movement.amount)} {native}{movement.asset}"


def wrong_asset_result(session: Any, movement: AssetMovement, txid: str) -> VerifyResult:
    request = session.request
    menu = session.config.enabled_networks()
    message = f"This transaction sends {name_the_asset(movement)} to your address, not {request.unit}."
    if movement.network in menu:
        message += f' That is payment method {menu.index(movement.network) + 1}, "{NETWORK_LABELS[movement.network]}".'
    message += f" This invoice is for {NETWORK_LABELS[request.network]}."
    return build_result(
        VerifyStatus.WRONG_TOKEN,
        Code.WRONG_ASSET_ON_RIGHT_ADDRESS,
        message,
        network=request.network,
        invoice_id=session.invoice_id,
        txid=txid,
        amount=movement.amount,
        confirmations=movement.confirmations,
        required_confirmations=movement.required_confirmations,
        block_height=movement.block_height,
    )


def not_accepted_result(session: Any, movement: AssetMovement, txid: str) -> VerifyResult:
    request = session.request
    message = (
        f"This transaction pays {name_the_asset(movement)} to your address on {NETWORK_LABELS[movement.network]}, "
        f"but this invoice cannot accept that option right now. This invoice is for {NETWORK_LABELS[request.network]}."
    )
    return build_result(
        VerifyStatus.WRONG_NETWORK,
        Code.ASSET_NOT_ACCEPTED,
        message,
        network=request.network,
        invoice_id=session.invoice_id,
        txid=txid,
        amount=movement.amount,
        confirmations=movement.confirmations,
        required_confirmations=movement.required_confirmations,
        block_height=movement.block_height,
    )


def cross_asset_note(movement: AssetMovement, result: VerifyResult) -> VerifyResult:
    if result.status in (VerifyStatus.CONFIRMED, VerifyStatus.DETECTED, VerifyStatus.UNDERPAID):
        result.message = (
            f"Paid with {name_the_asset(movement)} on {NETWORK_LABELS[movement.network]} "
            f"instead of the displayed method. {result.message}"
        )
    return result


async def settle_combined(session: Any, txid: str, matches: list[AssetMovement], on_update: Any, live: bool) -> VerifyResult:
    request = session.request
    options = {option.network: option for option in request.accepted}
    total_usd = Decimal(0)
    results: list[VerifyResult] = []
    for movement in matches:
        result = await session.reverify_for_amount(
            txid, options[movement.network].required_coin, on_update, live, network=movement.network
        )
        results.append(result)
        payload = await session.verifier.storage.recall_invoice_quote(session.invoice_id, movement.network.value)
        quote = quote_from_payload(payload)
        if result.status in (VerifyStatus.CONFIRMED, VerifyStatus.UNDERPAID) and result.amount and quote:
            total_usd += usd_value(result.amount, quote)
    best = max(results, key=lambda item: item.tier.value)
    assets = ", ".join(f"{display_amount(r.amount)} {NETWORK_UNITS[r.network]}" for r in results if r.amount and r.network)
    if session.usd_amount is not None and total_usd >= session.usd_amount:
        return build_result(
            VerifyStatus.CONFIRMED,
            Code.PAYMENT_FINAL,
            f"Invoice settled: one transaction paid {assets}, together worth ${usd_text(total_usd)} "
            f"against the ${usd_text(session.usd_amount)} invoice. Thank you.",
            network=request.network,
            invoice_id=session.invoice_id,
            txid=best.txid or txid,
            amount=best.amount,
            confirmations=best.confirmations,
            required_confirmations=best.required_confirmations,
            block_height=best.block_height,
            provider_used=best.provider_used,
        )
    short = (session.usd_amount - total_usd) if session.usd_amount is not None else Decimal(0)
    return build_result(
        VerifyStatus.UNDERPAID,
        Code.AMOUNT_BELOW_EXPECTED,
        f"One transaction paid {assets}, together worth ${usd_text(total_usd)}, but this invoice "
        f"needs ${usd_text(session.usd_amount or total_usd)}. Short by ${usd_text(short)}.",
        network=request.network,
        invoice_id=session.invoice_id,
        txid=best.txid or txid,
        amount=best.amount,
        confirmations=best.confirmations,
        required_confirmations=best.required_confirmations,
    )


async def route_submission(session: Any, txid: str, on_update: Any, live: bool) -> VerifyResult | None:
    request = session.request
    accepted = {option.network for option in request.accepted}
    if accepted <= {request.network}:
        return None
    identity = await session.verifier.identify(txid)
    paying = identity.paying_movements()
    if not paying:
        return None
    matches = [item for item in paying if item.network in accepted]
    if not matches:
        return not_accepted_result(session, paying[0], identity.txid)
    if not session.config.accept_any_configured_asset:
        if all(item.network is not request.network for item in matches):
            return wrong_asset_result(session, matches[0], identity.txid)
        matches = [item for item in matches if item.network is request.network]
    if len(matches) > 1:
        return await settle_combined(session, txid, matches, on_update, live)
    movement = matches[0]
    if movement.network is request.network:
        return None
    option = next(item for item in request.accepted if item.network is movement.network)
    result = await session.reverify_for_amount(txid, option.required_coin, on_update, live, network=movement.network)
    return cross_asset_note(movement, result)
