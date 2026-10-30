import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from cryptoverify import Network, VerifyResult, VerifyStatus
from cryptoverify.checkout_models import NETWORK_LABELS, NETWORK_UNITS, confirmations_text, display_amount

from config import (
    ADMIN_ID,
    ADMIN_USERNAME,
    CV_CONFIG,
    METHOD_EXPLORERS,
    METHOD_LABELS,
    NETWORK_BY_METHOD,
    PLANS,
    enabled_methods,
)
from database import get_awaiting_confirmation, get_daily_amount, get_setting, upsert_client
from keyboards.inline import (
    admin_confirm_reject,
    cancel_txid,
    payment_method,
    plan_daily_detail,
    plan_monthly_detail,
    plan_select,
    plan_weekly_detail,
    try_again,
    wallet_info,
)
from services import notifier, verifier
from states import HireStates
from utils.formatter import e, fmt_date, fmt_datetime

router = Router()


@router.callback_query(F.data == "hire_start")
async def hire_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    caption = (
        f'{e("🔒")} <b>Choose Your Plan</b>\n\n'
        "I work with a small number of clients\n"
        "at a time — so you get real focus,\n"
        "not divided attention.\n\n"
        "Tap a plan to see what's included."
    )
    await callback.message.edit_text(caption, parse_mode="HTML", reply_markup=plan_select())
    await callback.answer()


@router.callback_query(F.data == "plan_daily")
async def plan_daily(callback: CallbackQuery):
    daily_amount = await get_daily_amount()
    caption = (
        f'{e("🔥")} <b>Daily Plan</b>\n\n'
        "1 day of dedicated work on your project.\n"
        "Perfect for quick fixes and small tasks.\n\n"
        f'{e("⚡")} Full-time availability\n'
        f'{e("✅")} Priority support throughout\n'
        f'{e("✅")} Clean, deployable output\n\n'
        f'{e("🏷️")} <b>${daily_amount:g} / day</b>'
    )
    await callback.message.edit_text(caption, parse_mode="HTML", reply_markup=plan_daily_detail())
    await callback.answer()


@router.callback_query(F.data == "plan_weekly")
async def plan_weekly(callback: CallbackQuery):
    caption = (
        f'{e("📅")} <b>Weekly Plan</b>\n\n'
        "7 days of dedicated work on your project.\n"
        "I handle the build — you handle the vision.\n\n"
        f'{e("⚡")} Full-time availability\n'
        f'{e("✅")} Priority support throughout\n'
        f'{e("✅")} Clean, deployable output\n'
        f'{e("✅")} Revisions included\n\n'
        f'{e("🏷️")} <b>${PLANS["weekly"]["amount"]} / week</b>'
    )
    await callback.message.edit_text(caption, parse_mode="HTML", reply_markup=plan_weekly_detail())
    await callback.answer()


@router.callback_query(F.data == "plan_monthly")
async def plan_monthly(callback: CallbackQuery):
    caption = (
        f'{e("⭐")} <b>Monthly Plan</b>\n\n'
        "30 days. One client. Full focus.\n\n"
        "This is for projects that need\n"
        "more than a quick fix — workflows,\n"
        "bots, systems that quietly run\n"
        "in the background all day.\n\n"
        f'{e("⚡")} Full-time availability\n'
        f'{e("✅")} Long-term collaboration\n'
        f'{e("✅")} Unlimited revisions\n'
        f'{e("🎁")} Best value\n\n'
        f'{e("🏷️")} <b>${PLANS["monthly"]["amount"]} / month</b>'
    )
    await callback.message.edit_text(caption, parse_mode="HTML", reply_markup=plan_monthly_detail())
    await callback.answer()


async def _show_payment_method(callback: CallbackQuery, state: FSMContext, plan_key: str):
    plan = PLANS.get(plan_key)
    if plan is None:
        await callback.answer("Session expired — please start again with /start", show_alert=True)
        return
    methods = enabled_methods()
    if not methods:
        await callback.answer("No payment method is configured right now — contact support.", show_alert=True)
        return
    amount = await get_daily_amount() if plan_key == "daily" else plan["amount"]
    await state.update_data(plan=plan_key, amount=amount)
    await state.set_state(HireStates.payment_select)

    caption = (
        f'{e("💳")} <b>Payment</b>\n\n'
        f'Plan — <b>{plan["label"]} · ${amount:g}</b>\n\n'
        "Crypto only. Select your network below.\n"
        "Send the exact amount to avoid delays."
    )
    await callback.message.edit_text(caption, parse_mode="HTML", reply_markup=payment_method(plan_key, methods))
    await callback.answer()


@router.callback_query(F.data == "confirm_daily")
async def confirm_daily(callback: CallbackQuery, state: FSMContext):
    await _show_payment_method(callback, state, "daily")


@router.callback_query(F.data == "confirm_weekly")
async def confirm_weekly(callback: CallbackQuery, state: FSMContext):
    await _show_payment_method(callback, state, "weekly")


@router.callback_query(F.data == "confirm_monthly")
async def confirm_monthly(callback: CallbackQuery, state: FSMContext):
    await _show_payment_method(callback, state, "monthly")


@router.callback_query(F.data.startswith("pay_method_"))
async def pay_method_back(callback: CallbackQuery, state: FSMContext):
    plan_key = callback.data.removeprefix("pay_method_")
    await _show_payment_method(callback, state, plan_key)


def _wallet_caption(method: str, request) -> str:
    label = METHOD_LABELS[method]
    explorer, howto = METHOD_EXPLORERS[method]
    amount_line = f"{display_amount(request.amount)} {request.unit}"
    usd_line = f"  (≈ ${request.usd_amount})" if request.usd_amount is not None else ""
    return (
        f'{e("🔗")} <b>{label}</b>\n\n'
        f'{e("➡️")} Send exactly\n'
        f'<code>{amount_line}</code>{usd_line}\n\n'
        f'{e("💼")} To this address\n'
        f'<code>{request.address}</code>\n\n'
        f'{e("⚠️")} {label} network only.\n'
        "Wrong network means permanent loss — no recovery.\n\n"
        f'{e("ℹ️")} <b>How to find your TxID:</b>\n'
        f"Go to {explorer} → {howto}\n\n"
        f"Rate locked until <b>{request.expires_at.strftime('%H:%M UTC')}</b>.\n"
        "Once sent, tap below and submit your TxID."
    )


async def _show_wallet(callback: CallbackQuery, state: FSMContext, method: str):
    data = await state.get_data()
    plan_key = data.get("plan")
    amount = data.get("amount")
    if not plan_key or amount is None:
        await callback.answer("Session expired — please start again with /start", show_alert=True)
        return

    network = NETWORK_BY_METHOD[method]
    session = verifier.new_session()
    outcome = session.choose_network(network)
    if not outcome.ok:
        await callback.answer("That payment method is not available right now.", show_alert=True)
        return

    price_outcome = await session.set_usd_amount(amount)
    if not price_outcome.ok:
        await callback.answer(price_outcome.message or "Could not lock a rate — try again shortly.", show_alert=True)
        return

    await session.open_payment()
    await state.update_data(method=method, session=session)

    caption = _wallet_caption(method, session.request)
    await callback.message.edit_text(caption, parse_mode="HTML", reply_markup=wallet_info(plan_key))
    await callback.answer()


@router.callback_query(F.data.startswith("pay_") & ~F.data.startswith("pay_method_"))
async def pay_method(callback: CallbackQuery, state: FSMContext):
    method = callback.data.removeprefix("pay_")
    if method not in NETWORK_BY_METHOD:
        await callback.answer()
        return
    await _show_wallet(callback, state, method)


@router.callback_query(F.data == "submit_txid")
async def submit_txid(callback: CallbackQuery, state: FSMContext):
    await state.set_state(HireStates.awaiting_txid)
    caption = (
        f'{e("🔍")} <b>Transaction ID</b>\n\n'
        "Reply with your TxID — the transaction hash\n"
        "from your wallet's history.\n\n"
        f'{e("ℹ️")} Found in your wallet app\n'
        "under transaction history."
    )
    await callback.message.edit_text(caption, parse_mode="HTML", reply_markup=cancel_txid())
    await callback.answer()


@router.callback_query(F.data == "cancel_txid")
async def cancel_txid_handler(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    from handlers.start import send_welcome

    try:
        await callback.message.delete()
    except Exception:
        pass
    await send_welcome(callback.message, user_id=callback.from_user.id)
    await callback.answer()


def _verified_caption(plan: dict, amount: float, method: str, expires_at: datetime) -> str:
    return (
        f'{e("✅")} <b>You\'re In</b>\n\n'
        "Plan active. I'll reach out within\n"
        "1–2 hours to get things moving.\n\n"
        f'Plan     — <b>{plan["label"]}</b>\n'
        f"Amount   — <b>${amount}</b>\n"
        f"Method   — <b>{METHOD_LABELS[method]}</b>\n"
        f"Expires  — <b>{fmt_date(expires_at)}</b>\n\n"
        "Everything from here gets handled — cleanly.\n"
        f'{e("ℹ️")} Questions? Message — @{ADMIN_USERNAME}'
    )


def _under_review_caption(txid: str) -> str:
    return (
        f'{e("🕐")} <b>Under Review</b>\n\n'
        "TxID received.\n"
        "Verifying manually — usually done\n"
        "within 30 minutes.\n\n"
        f"TxID — <code>{txid}</code>\n\n"
        "You'll get a message once confirmed."
    )


def _verifying_caption(txid: str) -> str:
    return (
        f'{e("🔍")} <b>Verifying Transaction…</b>\n\n'
        "Checking your payment on-chain.\n"
        "This usually takes a few seconds.\n\n"
        f"TxID — <code>{txid}</code>"
    )


def _topup_caption(result: VerifyResult) -> str:
    return (
        f'{e("⚠️")} <b>Payment Short</b>\n\n'
        f"{result.message}\n\n"
        "Reply with the TxID of your top-up payment\n"
        "and I'll add it to the same invoice."
    )


def _progress_caption(txid: str, result: VerifyResult) -> str:
    conf_line = ""
    if result.confirmations and result.required_confirmations:
        conf_line = f'Confirms — <b>{confirmations_text(result.confirmations, result.required_confirmations)}</b>\n'
    return (
        f'{e("🕐")} <b>Confirming On-Chain</b>\n\n'
        f"{result.message}\n\n"
        f"{conf_line}"
        f"TxID     — <code>{txid}</code>"
    )


async def _update_status(bot, chat_id: int, message_id: int | None, text: str, reply_markup=None):
    """Edit the live status message if we have one, otherwise send a new message."""
    if message_id is not None:
        try:
            await bot.edit_message_text(
                chat_id=chat_id, message_id=message_id, text=text,
                parse_mode="HTML", reply_markup=reply_markup,
            )
            return
        except Exception:
            pass
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=reply_markup)
    except Exception:
        pass


def _admin_payment_caption(user, plan: dict, amount: float, method: str, result: VerifyResult, demo_mode: bool, when: datetime) -> str:
    reason = "Demo mode — verification skipped." if demo_mode else verifier.admin_reason(result)
    conf_line = ""
    if result.confirmations and result.required_confirmations:
        conf_line = f'Confirms — <b>{confirmations_text(result.confirmations, result.required_confirmations)}</b>\n'
    return (
        f'{e("🔔")} <b>New Payment Received</b>\n\n'
        f'{e("👤")} @{user.username or ""} · <code>{user.id}</code>\n'
        f'Plan    — <b>{plan["label"]} · ${amount}</b>\n'
        f"Method  — <b>{METHOD_LABELS[method]}</b>\n"
        f"TxID    — <code>{result.txid}</code>\n"
        f"Status  — <b>{result.status.value}</b>\n"
        f"{conf_line}"
        f"Reason  — {reason}\n"
        f'Demo    — <b>{"Yes" if demo_mode else "No"}</b>\n'
        f"Time    — <code>{fmt_datetime(when)}</code>"
    )


async def _activate_client(bot, user, plan_key: str, method: str, session: Any, result: VerifyResult, demo_mode: bool, amount, status_message_id: int | None = None):
    plan = PLANS[plan_key]
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=plan["days"])
    request = session.request
    await upsert_client(
        user_id=user.id,
        username=user.username or "",
        full_name=user.full_name,
        plan=plan_key,
        method=method,
        tx_id=result.txid,
        amount_usd=amount,
        status="active",
        auto_status=None,
        hired_at=now.isoformat(),
        expires_at=expires_at.isoformat(),
        reminded=0,
        demo=1 if demo_mode else 0,
        invoice_id=session.invoice_id,
        network=request.network.value,
        required_amount=str(request.amount),
        amount_paid_total=str(result.amount) if result.amount is not None else str(request.amount),
        invoice_created_at=request.created_at.isoformat() if request.created_at else "",
        invoice_expires_at=request.expires_at.isoformat() if request.expires_at else "",
        verify_status=result.status.value,
        verify_code=result.code,
        verify_message=result.message,
    )
    notifier.push("client_activated", {
        "user_id": user.id, "username": getattr(user, "username", "") or "",
        "plan": plan_key, "method": method, "amount": str(amount),
    })
    if not demo_mode:
        verifier.build_and_save_receipt(session, result)
    await _update_status(bot, user.id, status_message_id, _verified_caption(plan, amount, method, expires_at))
    try:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=_admin_payment_caption(user, plan, amount, method, result, demo_mode, now),
            parse_mode="HTML",
        )
    except Exception:
        logging.exception("Failed to notify admin about verified payment for user %s", user.id)


async def _flag_pending(bot, user, plan_key: str, method: str, session: Any, result: VerifyResult, demo_mode: bool, amount, status_message_id: int | None = None):
    plan = PLANS[plan_key]
    now = datetime.now(timezone.utc)
    request = session.request
    await upsert_client(
        user_id=user.id,
        username=user.username or "",
        full_name=user.full_name,
        plan=plan_key,
        method=method,
        tx_id=result.txid,
        amount_usd=amount,
        status="pending",
        auto_status=None,
        hired_at=now.isoformat(),
        expires_at=None,
        reminded=0,
        demo=1 if demo_mode else 0,
        invoice_id=session.invoice_id,
        network=request.network.value,
        required_amount=str(request.amount),
        amount_paid_total=str(getattr(session, "amount_paid_total", Decimal(0))),
        invoice_created_at=request.created_at.isoformat() if request.created_at else "",
        invoice_expires_at=request.expires_at.isoformat() if request.expires_at else "",
        verify_status=result.status.value,
        verify_code=result.code,
        verify_message=result.message,
    )
    notifier.push("client_pending", {
        "user_id": user.id, "username": getattr(user, "username", "") or "",
        "plan": plan_key, "method": method, "amount": str(amount),
    })
    await _update_status(bot, user.id, status_message_id, _under_review_caption(result.txid or ""))
    try:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=_admin_payment_caption(user, plan, amount, method, result, demo_mode, now),
            parse_mode="HTML",
            reply_markup=admin_confirm_reject(user.id),
        )
    except Exception:
        logging.exception("Failed to notify admin about pending payment for user %s", user.id)


async def _offer_topup(bot, state: FSMContext, user, plan_key: str, method: str, session: Any, result: VerifyResult, amount, status_message_id: int | None = None):
    plan = PLANS[plan_key]
    now = datetime.now(timezone.utc)
    request = session.request
    await upsert_client(
        user_id=user.id,
        username=user.username or "",
        full_name=user.full_name,
        plan=plan_key,
        method=method,
        tx_id=result.txid,
        amount_usd=amount,
        status="pending",
        auto_status="awaiting_topup",
        hired_at=now.isoformat(),
        expires_at=None,
        reminded=0,
        demo=0,
        invoice_id=session.invoice_id,
        network=request.network.value,
        required_amount=str(session.amount_remaining if session.amount_remaining is not None else request.amount),
        amount_paid_total=str(session.amount_paid_total),
        invoice_created_at=request.created_at.isoformat() if request.created_at else "",
        invoice_expires_at=request.expires_at.isoformat() if request.expires_at else "",
        verify_status=result.status.value,
        verify_code=result.code,
        verify_message=result.message,
    )
    notifier.push("topup_needed", {
        "user_id": user.id, "username": getattr(user, "username", "") or "",
        "plan": plan_key, "method": method, "amount": str(amount),
    })
    await state.update_data(plan=plan_key, method=method, session=session, amount=amount)
    await state.set_state(HireStates.awaiting_txid)
    await _update_status(bot, user.id, status_message_id, _topup_caption(result), reply_markup=cancel_txid())
    try:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=_admin_payment_caption(user, plan, amount, method, result, False, now),
            parse_mode="HTML",
        )
    except Exception:
        logging.exception("Failed to notify admin about a short payment for user %s", user.id)


async def _run_verification(bot, state: FSMContext, user, plan_key: str, method: str, session: Any, txid: str, demo_mode: bool, amount, status_message_id: int | None = None):
    if demo_mode:
        result = verifier.demo_result(session.request.network, session.request.amount, session.invoice_id, txid)
    else:
        async def on_update(update_result: VerifyResult):
            await _update_status(bot, user.id, status_message_id, _progress_caption(txid, update_result))

        try:
            result = await session.submit_txid_and_follow(txid, on_update=on_update)
        except Exception:
            logging.exception("verification crashed for user %s", user.id)
            result = verifier.error_result(session.request.network, session.invoice_id, txid)

    if result.status is VerifyStatus.CONFIRMED:
        await _activate_client(bot, user, plan_key, method, session, result, demo_mode, amount, status_message_id)
    elif result.status is VerifyStatus.UNDERPAID and CV_CONFIG.allow_partial_payments and not session.request.is_expired():
        await _offer_topup(bot, state, user, plan_key, method, session, result, amount, status_message_id)
    else:
        await _flag_pending(bot, user, plan_key, method, session, result, demo_mode, amount, status_message_id)


@router.message(HireStates.awaiting_txid)
async def receive_txid(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Please send your TxID as plain text.")
        return

    data = await state.get_data()
    plan_key = data.get("plan")
    method = data.get("method")
    session = data.get("session")
    amount = data.get("amount")
    if not plan_key or not method or session is None or amount is None:
        await state.clear()
        await message.answer("Session expired — please start again with /start")
        return

    txid = message.text.strip()
    if not txid or len(txid) > 128:
        await message.answer("That doesn't look like a valid TxID. Please send it again.")
        return

    await state.clear()

    # Instant feedback — the user sees verification happening live.
    status_msg = await message.answer(_verifying_caption(txid), parse_mode="HTML")
    status_message_id = status_msg.message_id

    demo_mode = (await get_setting("demo_mode")) == "true"
    user = message.from_user
    request = session.request
    now = datetime.now(timezone.utc)

    await upsert_client(
        user_id=user.id,
        username=user.username or "",
        full_name=user.full_name,
        plan=plan_key,
        method=method,
        tx_id=txid,
        amount_usd=amount,
        status="pending",
        auto_status="awaiting_confirmation",
        hired_at=now.isoformat(),
        expires_at=None,
        reminded=0,
        demo=1 if demo_mode else 0,
        invoice_id=session.invoice_id,
        network=request.network.value,
        required_amount=str(request.amount),
        amount_paid_total="0",
        invoice_created_at=request.created_at.isoformat() if request.created_at else "",
        invoice_expires_at=request.expires_at.isoformat() if request.expires_at else "",
        verify_status=None,
        verify_code=None,
        verify_message=None,
    )

    notifier.push("txid_received", {
        "user_id": user.id, "username": user.username or "",
        "plan": plan_key, "method": method, "amount": str(amount),
    })

    asyncio.create_task(
        _run_verification(message.bot, state, user, plan_key, method, session, txid, demo_mode, amount, status_message_id)
    )


@dataclass
class _StoredUser:
    id: int
    username: str
    full_name: str


@dataclass
class _ResumedRequest:
    network: Network
    amount: Decimal
    created_at: datetime | None
    expires_at: datetime | None
    label: str = ""
    unit: str = ""

    def is_expired(self, moment: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        return (moment or datetime.now(timezone.utc)) > self.expires_at


@dataclass
class _ResumedSession:
    invoice_id: str
    request: _ResumedRequest
    config: Any = field(default_factory=lambda: CV_CONFIG)
    amount_paid_total: Decimal = Decimal(0)
    amount_remaining: Decimal | None = None
    usd_amount: Decimal | None = None
    quote: Any = None
    payments: list = field(default_factory=list)


async def _resume_watch(bot, client):
    if not client["invoice_id"] or not client["network"] or not client["required_amount"]:
        return
    user = _StoredUser(id=client["user_id"], username=client["username"] or "", full_name=client["full_name"] or "")
    network = Network(client["network"])
    amount = Decimal(client["required_amount"])
    created_at = datetime.fromisoformat(client["invoice_created_at"]) if client["invoice_created_at"] else None
    expires_at = datetime.fromisoformat(client["invoice_expires_at"]) if client["invoice_expires_at"] else None
    remaining = (expires_at - datetime.now(timezone.utc)).total_seconds() if expires_at else CV_CONFIG.watch_timeout_minutes * 60
    if remaining <= 0:
        return

    result = await verifier.watch_existing(
        txid=client["tx_id"],
        network=network,
        amount=amount,
        invoice_id=client["invoice_id"],
        invoice_created_at=created_at,
        stop_after_seconds=remaining,
    )

    request = _ResumedRequest(
        network=network, amount=amount, created_at=created_at, expires_at=expires_at,
        label=NETWORK_LABELS.get(network, network.value), unit=NETWORK_UNITS.get(network, ""),
    )
    session = _ResumedSession(invoice_id=client["invoice_id"], request=request)
    demo_mode = bool(client["demo"])
    usd_amount = client["amount_usd"]

    if result.status is VerifyStatus.CONFIRMED:
        await _activate_client(bot, user, client["plan"], client["method"], session, result, demo_mode, usd_amount)
    else:
        await _flag_pending(bot, user, client["plan"], client["method"], session, result, demo_mode, usd_amount)


async def resume_pending_verifications(bot):
    clients = await get_awaiting_confirmation()
    for client in clients:
        asyncio.create_task(_resume_watch(bot, client))


async def send_rejection(bot, user_id: int, txid: str):
    caption = (
        f'{e("❌")} <b>Payment Not Confirmed</b>\n\n'
        "Your transaction could not be verified.\n\n"
        f"TxID — <code>{txid}</code>\n\n"
        f'{e("ℹ️")} If you believe this is an error,\n'
        f"contact directly — @{ADMIN_USERNAME}\n\n"
        "You can start a new payment below."
    )
    await bot.send_message(chat_id=user_id, text=caption, parse_mode="HTML", reply_markup=try_again())
