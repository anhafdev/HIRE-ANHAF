import asyncio
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import ADMIN_ID, PLANS
from database import get_active, set_reminded, set_status
from keyboards.inline import renew_button
from utils.formatter import e, fmt_date

scheduler = AsyncIOScheduler()

_bot = None


def init_scheduler(bot):
    global _bot
    _bot = bot

    @scheduler.scheduled_job("interval", hours=1)
    async def check_reminders():
        active_clients = await get_active()
        now = datetime.now(timezone.utc)

        for client in active_clients:
            try:
                try:
                    expires_at = datetime.fromisoformat(client["expires_at"]).replace(tzinfo=timezone.utc)
                except (TypeError, ValueError):
                    continue
                remind_before = PLANS[client["plan"]]["remind_before"]
                days_left = (expires_at - now).days

                if (
                    remind_before > 0
                    and days_left <= remind_before
                    and not client["reminded"]
                    and expires_at > now
                ):
                    try:
                        await _bot.send_message(
                            chat_id=client["user_id"],
                            text=_build_reminder_caption(client, days_left),
                            parse_mode="HTML",
                            reply_markup=renew_button(),
                        )
                    except Exception:
                        pass
                    await set_reminded(client["user_id"])
                    await asyncio.sleep(0.05)

                if expires_at <= now and client["status"] == "active":
                    await set_status(client["user_id"], "expired")
                    await _notify_user_expired(client)
                    await _notify_admin_expired(client)
                    await asyncio.sleep(0.05)
            except Exception:
                logging.exception("Scheduler failed for client %s", client["user_id"])

    return scheduler


def _build_reminder_caption(client, days_left: int) -> str:
    plan_label = PLANS[client["plan"]]["label"]
    expires_date = fmt_date(client["expires_at"])
    return (
        f'{e("🔔")} <b>Heads Up</b>\n\n'
        f'{e("⚠️")} Your plan expires in <b>{days_left} days</b>.\n\n'
        f"Plan    — <b>{plan_label}</b>\n"
        f"Expires — <b>{expires_date}</b>\n\n"
        "Renew now to keep things running\n"
        "without a gap."
    )


async def _notify_user_expired(client):
    try:
        await _bot.send_message(
            chat_id=client["user_id"],
            text=f'{e("ℹ️")} <b>Plan Ended</b>\n\nYour access has ended. Thanks for working with me.',
            parse_mode="HTML",
            reply_markup=renew_button(),
        )
    except Exception:
        pass


async def _notify_admin_expired(client):
    try:
        await _bot.send_message(
            chat_id=ADMIN_ID,
            text=f'{e("❌")} <b>Plan Expired</b>\n\n@{client["username"]} · <code>{client["user_id"]}</code>',
            parse_mode="HTML",
        )
    except Exception:
        pass
