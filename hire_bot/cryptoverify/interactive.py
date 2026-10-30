from __future__ import annotations

import asyncio

from .checkout import CheckoutSession, NETWORK_UNITS
from .checkout_models import NETWORK_LABELS, confirmations_text
from .config import Config
from .models import VerifyResult, VerifyStatus
from .receipt import build_receipt, save_receipt_files
from .spinner import Spinner, with_spinner
from .verifier import DepositVerifier
from .watcher import next_pause

DIVIDER = "-" * 46
STILL_WAITING = {VerifyStatus.NOT_FOUND, VerifyStatus.DETECTED, VerifyStatus.PROVIDER_UNAVAILABLE}
QUIT_WORDS = {"q", "quit", "exit"}


async def ask(prompt: str) -> str:
    answer = await asyncio.to_thread(input, prompt)
    return answer.strip()


def show(*lines: str) -> None:
    for line in lines:
        print(line)


async def pick_method(session: CheckoutSession) -> bool:
    options = session.menu()
    if not options:
        show("No deposit address is configured. Fill CV_ADDR_BTC, CV_ADDR_TRC20, CV_ADDR_BEP20, CV_ADDR_ETH or CV_ADDR_ERC20 in your .env first.")
        return False
    show("", "Select a payment method:")
    for number, _, label in options:
        show(f"  {number}) {label}")
    while True:
        answer = await ask("> ")
        if answer.lower() in QUIT_WORDS:
            return False
        outcome = session.choose_network(answer)
        show(outcome.message)
        if outcome.ok:
            return True


async def pick_amount(session: CheckoutSession) -> bool:
    while True:
        answer = await ask("Amount in USD: ")
        if answer.lower() in QUIT_WORDS:
            return False
        outcome = await with_spinner("Fetching the live exchange rate", session.set_usd_amount(answer))
        show(outcome.message)
        if outcome.ok:
            show(f"You will be charged {session.amount} {NETWORK_UNITS[session.network]}")
            return True


async def present_address(session: CheckoutSession) -> bool:
    outcome = await with_spinner("Preparing your invoice", session.open_payment())
    if not outcome.ok or session.request is None:
        show(outcome.message)
        return False
    request = session.request
    show("", DIVIDER, *request.as_lines(), DIVIDER)
    if request.shared_address_with:
        also = ", ".join(NETWORK_LABELS[item] for item in request.shared_address_with)
        show(f"NOTE  This address is also used for: {also}.")
        show("      Tell your client the ASSET and the NETWORK, not just the address.")
    show(f"Send {request.amount} {request.unit} or more to the address above.")
    show(f"Final after {request.required_confirmations} confirmation(s).")
    return True


def print_transition(result) -> None:
    show(f"  [{result.status.value}] {result.message}")


def cadence_hint(elapsed: float) -> str:
    return f"next check in ~{next_pause(elapsed):0.0f}s"


async def watch_with_spinner(session: CheckoutSession, txid: str) -> VerifyResult:
    spinner = Spinner()

    async def on_update(result: VerifyResult) -> None:
        await spinner.pause()
        print_transition(result)
        spinner.start(f"Watching for [{result.status.value}] to change", cadence_hint)

    spinner.start("Checking the network", cadence_hint)
    try:
        return await session.submit_txid_and_follow(txid, on_update=on_update)
    finally:
        await spinner.stop()


def print_receipt(session: CheckoutSession, result) -> None:
    receipt = build_receipt(session, result)
    show("", receipt.as_text())
    if session.config.receipt_dir:
        save_receipt_files(receipt, session.config.receipt_dir)


def explain_stop(session: CheckoutSession) -> None:
    if session.request is not None and session.request.is_expired():
        show("Stopped because the invoice expired. Start a new payment.")
    else:
        show(f"Stopped because the watch window of {session.config.watch_timeout_minutes} minute(s) ended. The hash can be re-checked later.")


async def collect_and_verify(session: CheckoutSession) -> bool:
    txid = await ask("Transaction hash: ")
    while True:
        if txid.lower() in QUIT_WORDS:
            return False
        if not txid:
            txid = await ask("Transaction hash: ")
            continue
        show("Watching the chain until this settles. Ctrl+C stops.")
        result = await watch_with_spinner(session, txid)
        show("", DIVIDER, f"Status     {result.status.value}", f"Code       {result.code}")
        if result.amount is not None:
            show(f"Received   {result.amount}")
        show(f"Confirmed  {confirmations_text(result.confirmations, result.required_confirmations)}", DIVIDER, result.message)
        if result.status is VerifyStatus.CONFIRMED:
            print_receipt(session, result)
            return True
        if result.status is VerifyStatus.UNDERPAID and session.config.allow_partial_payments:
            txid = await ask("Next transaction hash: ")
            continue
        if result.status in STILL_WAITING:
            explain_stop(session)
        return False


async def run_wizard(config: Config | None = None, verifier: DepositVerifier | None = None) -> int:
    owned = verifier is None
    active = verifier or DepositVerifier(config or Config.from_env())
    session = CheckoutSession(active)
    try:
        show("cryptoverify payment checkout")
        if not await pick_method(session):
            return 1
        if not await pick_amount(session):
            return 1
        if not await present_address(session):
            return 1
        settled = await collect_and_verify(session)
        show("Payment complete." if settled else "Payment not completed.")
        return 0 if settled else 1
    except (KeyboardInterrupt, EOFError):
        last = session.result.status.value if session.result else "no verification yet"
        show("", f"Stopped. Last status: {last}")
        return 130
    finally:
        if owned:
            await active.close()
