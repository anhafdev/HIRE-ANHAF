from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from config import PLANS
from database import get_client
from keyboards.inline import welcome_active, welcome_new, welcome_pending
from utils.formatter import e, fmt_date

router = Router()


def _welcome_new_caption() -> str:
    return (
        f'{e("👑")} <b>Algo Anhaf</b>\n\n'
        "I build Python automation solutions —\n"
        "Telegram bots, web scrapers, APIs,\n"
        "and backend systems that run on their own.\n\n"
        "Over 2.5 years. 10 orders. Every one, 5 stars.\n\n"
        "If you need something built clean\n"
        "and ready to deploy — you're in the right place."
    )


def _welcome_active_caption(client) -> str:
    plan_label = PLANS[client["plan"]]["label"]
    expires_date = fmt_date(client["expires_at"])
    return (
        f'{e("👑")} <b>Welcome back.</b>\n\n'
        f'{e("✅")} Your plan is active.\n\n'
        f"Plan     — <b>{plan_label}</b>\n"
        "Status   — <b>Active</b>\n"
        f"Expires  — <b>{expires_date}</b>"
    )


def _welcome_pending_caption(client) -> str:
    return (
        f'{e("🕐")} <b>Payment Under Review</b>\n\n'
        "Your previous payment is still being verified.\n"
        "You'll be notified once confirmed.\n\n"
        f'TxID — <code>{client["tx_id"]}</code>'
    )


async def send_welcome(message: Message, user_id: int | None = None):
    client = await get_client(user_id if user_id is not None else message.from_user.id)

    if client is None:
        await message.answer(_welcome_new_caption(), parse_mode="HTML", reply_markup=welcome_new())
        return

    if client["status"] == "active":
        await message.answer(
            _welcome_active_caption(client), parse_mode="HTML", reply_markup=welcome_active()
        )
        return

    if client["status"] == "pending":
        await message.answer(
            _welcome_pending_caption(client), parse_mode="HTML", reply_markup=welcome_pending()
        )
        return

    await message.answer(_welcome_new_caption(), parse_mode="HTML", reply_markup=welcome_new())


@router.message(CommandStart())
async def cmd_start(message: Message):
    await send_welcome(message)


@router.callback_query(F.data == "back_to_start")
async def back_to_start(callback: CallbackQuery):
    client = await get_client(callback.from_user.id)

    if client is None or client["status"] not in ("active", "pending"):
        await callback.message.edit_text(
            _welcome_new_caption(), parse_mode="HTML", reply_markup=welcome_new()
        )
    elif client["status"] == "active":
        await callback.message.edit_text(
            _welcome_active_caption(client), parse_mode="HTML", reply_markup=welcome_active()
        )
    else:
        await callback.message.edit_text(
            _welcome_pending_caption(client), parse_mode="HTML", reply_markup=welcome_pending()
        )

    await callback.answer()


@router.callback_query(F.data == "my_status")
async def my_status(callback: CallbackQuery):
    client = await get_client(callback.from_user.id)
    if client is None or client["status"] != "active":
        await callback.answer("No active plan found.", show_alert=True)
        return

    await callback.message.edit_text(
        _welcome_active_caption(client), parse_mode="HTML", reply_markup=welcome_active()
    )
    await callback.answer()
