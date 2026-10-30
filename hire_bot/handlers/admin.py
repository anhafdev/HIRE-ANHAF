import asyncio
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from config import ADMIN_ID, ADMIN_USERNAME, DASHBOARD_IMAGE, METHOD_LABELS, PLANS
from database import (
    get_active,
    get_all_clients,
    get_client,
    get_daily_amount,
    get_pending,
    get_revenue_this_month,
    get_setting,
    set_daily_amount,
    set_expires_at,
    set_setting,
    set_status,
)
from handlers.hire import send_rejection
from services import notifier
from keyboards.inline import admin_active_list, admin_cancel_broadcast, admin_settings_menu, admin_user_detail
from keyboards.reply import admin_main_menu
from states import AdminStates
from utils.formatter import e, fmt_date, fmt_datetime

router = Router()
router.message.filter(F.from_user.id == ADMIN_ID)
router.callback_query.filter(F.from_user.id == ADMIN_ID)


DASHBOARD_REFRESH_SECONDS = 4
DASHBOARD_LIVE_DURATION_SECONDS = 600

MAX_MESSAGE_LENGTH = 4000  # Telegram hard limit is 4096; keep headroom for HTML tags
MAX_KEYBOARD_BUTTONS = 100  # Telegram inline keyboard limit
BROADCAST_DELAY_SECONDS = 0.05  # ~20 msg/sec, under Telegram's ~30/sec flood limit


async def _send_chunked(message: Message, lines: list[str]):
    """Send lines as multiple messages, each under Telegram's 4096-char limit."""
    chunk: list[str] = []
    size = 0
    for line in lines:
        if chunk and size + len(line) + 1 > MAX_MESSAGE_LENGTH:
            await message.answer("\n".join(chunk), parse_mode="HTML")
            chunk, size = [], 0
        chunk.append(line)
        size += len(line) + 1
    if chunk:
        await message.answer("\n".join(chunk), parse_mode="HTML")


async def _build_dashboard_caption() -> str:
    all_clients = await get_all_clients()
    active = [c for c in all_clients if c["status"] == "active"]
    pending = [c for c in all_clients if c["status"] == "pending"]
    expired = [c for c in all_clients if c["status"] == "expired"]
    rejected = [c for c in all_clients if c["status"] == "rejected"]
    daily_active = [c for c in active if c["plan"] == "daily"]
    weekly_active = [c for c in active if c["plan"] == "weekly"]
    monthly_active = [c for c in active if c["plan"] == "monthly"]
    revenue = await get_revenue_this_month()

    return (
        f'{e("📊")} <b>Dashboard</b>\n'
        f"<code>{fmt_datetime(datetime.now(timezone.utc))}</code>\n\n"
        f'{e("👥")} <b>Overview</b>\n'
        f"Total Users     — <b>{len(all_clients)}</b>\n"
        f"Active Plans    — <b>{len(active)}</b>\n"
        f"Pending Verify  — <b>{len(pending)}</b>\n"
        f"Expired         — <b>{len(expired)}</b>\n"
        f"Rejected        — <b>{len(rejected)}</b>\n\n"
        f'{e("🏷️")} <b>Plan Breakdown</b>\n'
        f'{e("🔥")} Daily    — <b>{len(daily_active)}</b> active\n'
        f'{e("📅")} Weekly   — <b>{len(weekly_active)}</b> active\n'
        f'{e("⭐")} Monthly  — <b>{len(monthly_active)}</b> active\n\n'
        f'{e("💰")} <b>Revenue This Month</b>\n'
        f"<b>${revenue}</b>"
    )


async def _run_live_dashboard(bot, chat_id: int, message_id: int):
    ticks = DASHBOARD_LIVE_DURATION_SECONDS // DASHBOARD_REFRESH_SECONDS
    for _ in range(ticks):
        await asyncio.sleep(DASHBOARD_REFRESH_SECONDS)
        try:
            caption = await _build_dashboard_caption()
            await bot.edit_message_caption(chat_id=chat_id, message_id=message_id, caption=caption, parse_mode="HTML")
        except TelegramBadRequest:
            continue
        except Exception:
            return


@router.message(CommandStart())
async def admin_start(message: Message):
    caption = f'{e("🛡️")} <b>Admin Panel</b>\n\nWelcome back, Anhaf.'
    await message.answer(caption, parse_mode="HTML", reply_markup=admin_main_menu())

    dashboard_caption = await _build_dashboard_caption()
    dashboard_msg = await message.answer_photo(
        FSInputFile(DASHBOARD_IMAGE), caption=dashboard_caption, parse_mode="HTML"
    )
    asyncio.create_task(_run_live_dashboard(message.bot, dashboard_msg.chat.id, dashboard_msg.message_id))


@router.message(F.text.contains("Dashboard"))
async def dashboard(message: Message):
    caption = await _build_dashboard_caption()
    dashboard_msg = await message.answer_photo(
        FSInputFile(DASHBOARD_IMAGE), caption=caption, parse_mode="HTML"
    )
    asyncio.create_task(_run_live_dashboard(message.bot, dashboard_msg.chat.id, dashboard_msg.message_id))


@router.message(F.text.contains("Pending"))
async def pending_list(message: Message):
    pending = await get_pending()

    if not pending:
        caption = f'{e("✅")} <b>No Pending Payments</b>\n\nAll clear — nothing to verify right now.'
        await message.answer(caption, parse_mode="HTML")
        return

    from keyboards.inline import admin_confirm_reject

    for client in pending:
        plan = PLANS[client["plan"]]
        status_line = ""
        if client["verify_status"]:
            status_line = f'Status  — <b>{client["verify_status"]}</b>\n'
            if client["verify_message"]:
                status_line += f'Reason  — {client["verify_message"]}\n'
        caption = (
            f'{e("🕐")} <b>Pending Payment</b>\n\n'
            f'{e("👤")} @{client["username"]} · <code>{client["user_id"]}</code>\n'
            f'Plan    — <b>{plan["label"]} · ${client["amount_usd"]}</b>\n'
            f'Method  — <b>{METHOD_LABELS.get(client["method"], client["method"])}</b>\n'
            f'TxID    — <code>{client["tx_id"]}</code>\n'
            f'{status_line}'
            f'Time    — <code>{fmt_datetime(client["hired_at"])}</code>'
        )
        await message.answer(
            caption, parse_mode="HTML", reply_markup=admin_confirm_reject(client["user_id"])
        )
        await asyncio.sleep(BROADCAST_DELAY_SECONDS)


@router.message(F.text.contains("Active"))
async def active_list(message: Message):
    await _send_active_list(message)


async def _send_active_list(message: Message):
    active = await get_active()

    if not active:
        caption = f'{e("ℹ️")} <b>No Active Clients</b>\n\nNobody hired right now.'
        await message.answer(caption, parse_mode="HTML")
        return

    lines = [f'{e("✅")} <b>Active Clients · {len(active)}</b>\n']
    for client in active:
        plan_label = PLANS[client["plan"]]["label"]
        lines.append(
            f'{e("👤")} @{client["username"]} — <b>{plan_label}</b> — expires <b>{fmt_date(client["expires_at"])}</b>'
        )

    if len(active) > MAX_KEYBOARD_BUTTONS:
        # Too many for one inline keyboard — send the list as text only.
        await _send_chunked(message, lines)
        await message.answer(
            f'{e("ℹ️")} List too long for buttons — use user IDs above.', parse_mode="HTML"
        )
        return

    caption = "\n".join(lines)
    pairs = [(c["user_id"], c["username"]) for c in active]
    if len(caption) > MAX_MESSAGE_LENGTH:
        await _send_chunked(message, lines)
        caption = f'{e("👥")} Select a client:'
    await message.answer(caption, parse_mode="HTML", reply_markup=admin_active_list(pairs))


@router.callback_query(F.data == "admin_active_list")
async def admin_active_list_cb(callback: CallbackQuery):
    await callback.message.delete()
    await _send_active_list(callback.message)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_user_"))
async def admin_user_detail_cb(callback: CallbackQuery):
    user_id = int(callback.data.removeprefix("admin_user_"))
    await _show_user_detail(callback, user_id)


async def _show_user_detail(callback: CallbackQuery, user_id: int):
    client = await get_client(user_id)
    if client is None:
        await callback.answer()
        return

    plan_label = PLANS[client["plan"]]["label"]
    verify_line = f'Verify   — <b>{client["verify_status"]}</b>\n' if client["verify_status"] else ""
    paid_line = ""
    if client["required_amount"]:
        paid = client["amount_paid_total"] or "0"
        paid_line = f'Paid     — <b>{paid} / {client["required_amount"]}</b>\n'
    caption = (
        f'{e("👤")} <b>@{client["username"]}</b>\n\n'
        f'ID       — <code>{client["user_id"]}</code>\n'
        f'Name     — <b>{client["full_name"]}</b>\n'
        f"Plan     — <b>{plan_label}</b>\n"
        f'Status   — <b>{client["status"]}</b>\n'
        f'Hired    — <b>{fmt_date(client["hired_at"])}</b>\n'
        f'Expires  — <b>{fmt_date(client["expires_at"])}</b>\n'
        f'Method   — <b>{METHOD_LABELS.get(client["method"], client["method"])}</b>\n'
        f'TxID     — <code>{client["tx_id"]}</code>\n'
        f'{verify_line}'
        f'{paid_line}'
        f'Demo     — <b>{"Yes" if client["demo"] else "No"}</b>'
    )
    await callback.message.edit_text(caption, parse_mode="HTML", reply_markup=admin_user_detail(user_id))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_confirm_"))
async def admin_confirm(callback: CallbackQuery):
    user_id = int(callback.data.removeprefix("admin_confirm_"))
    client = await get_client(user_id)
    if client is None:
        await callback.answer()
        return

    plan = PLANS[client["plan"]]
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=plan["days"])

    await set_status(user_id, "active")
    await set_expires_at(user_id, expires_at.isoformat())
    notifier.push("client_updated", {"user_id": user_id, "status": "active"})

    caption = (
        f'{e("✅")} <b>You\'re In</b>\n\n'
        "Plan active. I'll reach out within\n"
        "1–2 hours to get things moving.\n\n"
        f'Plan     — <b>{plan["label"]}</b>\n'
        f'Amount   — <b>${client["amount_usd"]}</b>\n'
        f'Method   — <b>{client["method"]}</b>\n'
        f"Expires  — <b>{fmt_date(expires_at)}</b>\n\n"
        "Everything from here gets handled — cleanly.\n"
        f'{e("ℹ️")} Questions? Message — @{ADMIN_USERNAME}'
    )
    try:
        await callback.bot.send_message(chat_id=user_id, text=caption, parse_mode="HTML")
    except Exception:
        pass
    await callback.message.edit_text(f'Confirmed {e("✅")} — @{client["username"]}', parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_reject_"))
async def admin_reject(callback: CallbackQuery):
    user_id = int(callback.data.removeprefix("admin_reject_"))
    client = await get_client(user_id)
    if client is None:
        await callback.answer()
        return

    await set_status(user_id, "rejected")
    notifier.push("client_updated", {"user_id": user_id, "status": "rejected"})
    try:
        await send_rejection(callback.bot, user_id, client["tx_id"])
    except Exception:
        pass
    await callback.message.edit_text(f'Rejected {e("❌")} — @{client["username"]}', parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_revoke_"))
async def admin_revoke(callback: CallbackQuery):
    user_id = int(callback.data.removeprefix("admin_revoke_"))
    client = await get_client(user_id)
    if client is None:
        await callback.answer()
        return

    await set_status(user_id, "expired")
    notifier.push("client_updated", {"user_id": user_id, "status": "expired"})
    caption = f'{e("ℹ️")} <b>Plan Ended</b>\n\nYour access has ended. Thanks for working with me.'
    try:
        await callback.bot.send_message(chat_id=user_id, text=caption, parse_mode="HTML")
    except Exception:
        pass
    await callback.answer("Revoked")
    await _show_user_detail(callback, user_id)


@router.callback_query(F.data.startswith("admin_extend_"))
async def admin_extend(callback: CallbackQuery):
    user_id = int(callback.data.removeprefix("admin_extend_"))
    client = await get_client(user_id)
    if client is None:
        await callback.answer()
        return

    plan = PLANS[client["plan"]]
    now = datetime.now(timezone.utc)
    if client["expires_at"]:
        current_expiry = datetime.fromisoformat(client["expires_at"])
        if current_expiry < now:
            current_expiry = now
    else:
        current_expiry = now
    new_expiry = current_expiry + timedelta(days=plan["days"])
    await set_expires_at(user_id, new_expiry.isoformat())
    notifier.push("client_updated", {"user_id": user_id})

    caption = (
        f'{e("📅")} <b>Plan Extended</b>\n\n'
        f"Your plan now runs until <b>{fmt_date(new_expiry)}</b>."
    )
    try:
        await callback.bot.send_message(chat_id=user_id, text=caption, parse_mode="HTML")
    except Exception:
        pass
    await callback.answer("Extended")
    await _show_user_detail(callback, user_id)


@router.callback_query(F.data.startswith("admin_message_"))
async def admin_message_start(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.removeprefix("admin_message_"))
    await state.update_data(target_user_id=user_id)
    await state.set_state(AdminStates.awaiting_message)
    await callback.message.answer(f'{e("📩")} Type the message to send to this client.', parse_mode="HTML")
    await callback.answer()


@router.message(AdminStates.awaiting_message)
async def admin_message_send(message: Message, state: FSMContext):
    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    await state.clear()
    if target_user_id is None:
        await message.answer(f'{e("❌")} No target selected — try again.', parse_mode="HTML")
        return
    if not message.text:
        await message.answer(f'{e("❌")} Only plain text messages are supported.', parse_mode="HTML")
        return
    try:
        await message.bot.send_message(chat_id=target_user_id, text=message.text)
        await message.answer(f'{e("✅")} Message sent.', parse_mode="HTML")
    except Exception:
        await message.answer(f'{e("❌")} Could not deliver — user may have blocked the bot.', parse_mode="HTML")


@router.message(F.text.contains("Broadcast"))
async def broadcast_start(message: Message, state: FSMContext):
    await state.set_state(AdminStates.awaiting_broadcast)
    caption = f'{e("📩")} <b>Broadcast</b>\n\nType your message below.\nIt will be sent to all users in the database.'
    await message.answer(caption, parse_mode="HTML", reply_markup=admin_cancel_broadcast())


@router.callback_query(F.data == "admin_cancel_broadcast")
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(f'{e("❌")} Broadcast cancelled.', parse_mode="HTML")
    await callback.answer()


@router.message(AdminStates.awaiting_broadcast)
async def broadcast_send(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Broadcast must be plain text. Send it again.")
        return

    await state.clear()
    clients = await get_all_clients()
    status_msg = await message.answer(f'{e("📩")} Broadcasting to {len(clients)} users…', parse_mode="HTML")

    sent = 0
    failed = 0
    for client in clients:
        try:
            await message.bot.send_message(chat_id=client["user_id"], text=message.text)
            sent += 1
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
            try:
                await message.bot.send_message(chat_id=client["user_id"], text=message.text)
                sent += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1
        await asyncio.sleep(BROADCAST_DELAY_SECONDS)

    try:
        await status_msg.edit_text(
            f'{e("✅")} Broadcast done — sent to {sent} users, {failed} failed.', parse_mode="HTML"
        )
    except Exception:
        await message.answer(
            f'{e("✅")} Broadcast done — sent to {sent} users, {failed} failed.', parse_mode="HTML"
        )


async def _settings_caption(demo_mode: bool) -> str:
    daily_amount = await get_daily_amount()
    return (
        f'{e("⚙️")} <b>Settings</b>\n\n'
        f'{e("🧪")} Demo Mode — <b>{"ON" if demo_mode else "OFF"}</b>\n'
        f'{e("🔥")} Daily Price — <b>${daily_amount:g}</b>\n\n'
        "When Demo Mode is ON:\n"
        "Any TxID is accepted instantly. Nothing is checked on-chain.\n"
        "Useful for testing the full user flow.\n\n"
        "When Demo Mode is OFF:\n"
        "Full cryptoverify verification — locked USD rate, zero-tolerance\n"
        "amount, replay/freshness checks, cross-chain and any-asset detection."
    )


@router.message(F.text.contains("Settings"))
async def settings_menu(message: Message):
    demo_mode = (await get_setting("demo_mode")) == "true"
    caption = await _settings_caption(demo_mode)
    await message.answer(caption, parse_mode="HTML", reply_markup=admin_settings_menu(demo_mode))


@router.callback_query(F.data == "admin_toggle_demo")
async def admin_toggle_demo(callback: CallbackQuery):
    demo_mode = (await get_setting("demo_mode")) == "true"
    new_value = "false" if demo_mode else "true"
    await set_setting("demo_mode", new_value)
    notifier.push("settings_changed", {"demo_mode": new_value})
    new_demo_mode = new_value == "true"

    caption = await _settings_caption(new_demo_mode)
    await callback.message.edit_text(caption, parse_mode="HTML", reply_markup=admin_settings_menu(new_demo_mode))
    await callback.answer()


@router.callback_query(F.data == "admin_set_daily_amount")
async def admin_set_daily_amount_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.awaiting_daily_amount)
    await callback.message.answer(
        f'{e("🔥")} Send the new Daily plan price in USD (e.g. 25).', parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.awaiting_daily_amount)
async def admin_set_daily_amount_save(message: Message, state: FSMContext):
    await state.clear()
    try:
        amount = float((message.text or "").strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer(f'{e("❌")} Enter a valid positive number.', parse_mode="HTML")
        return

    await set_daily_amount(amount)
    notifier.push("settings_changed", {"daily_amount": amount})
    demo_mode = (await get_setting("demo_mode")) == "true"
    caption = await _settings_caption(demo_mode)
    await message.answer(f'{e("✅")} Daily price updated to <b>${amount:g}</b>.', parse_mode="HTML")
    await message.answer(caption, parse_mode="HTML", reply_markup=admin_settings_menu(demo_mode))


@router.message(F.text.contains("Users"))
async def users_list(message: Message):
    clients = await get_all_clients()
    if not clients:
        await message.answer(f'{e("ℹ️")} No users yet.', parse_mode="HTML")
        return

    lines = [f'{e("👥")} <b>All Users · {len(clients)}</b>\n']
    for client in clients:
        lines.append(f'{e("👤")} @{client["username"]} — <b>{client["status"]}</b>')
    await _send_chunked(message, lines)
