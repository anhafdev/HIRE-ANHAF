import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx

import settings

logger = logging.getLogger(__name__)
TG_API = "https://api.telegram.org"


async def tg_send(chat_id: int, text: str, parse_mode: str = "HTML") -> bool:
    if not settings.BOT_TOKEN:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{TG_API}/bot{settings.BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            )
            return resp.status_code == 200
    except Exception:
        logger.exception("telegram send failed for %s", chat_id)
        return False


def get_client(user_id: int) -> dict | None:
    db = settings.connect()
    try:
        row = db.execute("SELECT * FROM clients WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        db.close()


def _set(user_id: int, **fields):
    cols = ", ".join(f"{k} = ?" for k in fields)
    db = settings.connect()
    try:
        db.execute(f"UPDATE clients SET {cols} WHERE user_id = ?", (*fields.values(), user_id))
        db.commit()
    finally:
        db.close()


async def approve(user_id: int) -> dict:
    client = get_client(user_id)
    if client is None:
        return {"ok": False, "error": "client not found"}
    days = settings.PLAN_DAYS.get(client["plan"], 1)
    expires_at = datetime.now(timezone.utc) + timedelta(days=days)
    _set(user_id, status="active", auto_status=None, expires_at=expires_at.isoformat(),
         reminded=0)
    label = settings.PLAN_LABELS.get(client["plan"], client["plan"])
    await tg_send(
        user_id,
        f"<b>You\'re In</b>\n\nPlan active. I\'ll reach out within 1-2 hours.\n\n"
        f"Plan — <b>{label}</b>\nAmount — <b>${client['amount_usd']}</b>\n"
        f"Expires — <b>{expires_at.strftime('%d %b %Y')}</b>",
    )
    return {"ok": True, "status": "active", "expires_at": expires_at.isoformat()}


async def reject(user_id: int) -> dict:
    client = get_client(user_id)
    if client is None:
        return {"ok": False, "error": "client not found"}
    _set(user_id, status="rejected", auto_status=None)
    await tg_send(
        user_id,
        "<b>Payment Not Confirmed</b>\n\nYour transaction could not be verified.\n\n"
        f"TxID — <code>{client['tx_id']}</code>\n\nSend /start to try a new payment.",
    )
    return {"ok": True, "status": "rejected"}


async def revoke(user_id: int) -> dict:
    client = get_client(user_id)
    if client is None:
        return {"ok": False, "error": "client not found"}
    _set(user_id, status="expired")
    await tg_send(user_id, "<b>Plan Ended</b>\n\nYour access has ended. Thanks for working with me.")
    return {"ok": True, "status": "expired"}


async def extend(user_id: int) -> dict:
    client = get_client(user_id)
    if client is None:
        return {"ok": False, "error": "client not found"}
    days = settings.PLAN_DAYS.get(client["plan"], 1)
    now = datetime.now(timezone.utc)
    try:
        current = datetime.fromisoformat(client["expires_at"]) if client["expires_at"] else now
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        if current < now:
            current = now
    except (ValueError, TypeError):
        current = now
    new_expiry = current + timedelta(days=days)
    _set(user_id, expires_at=new_expiry.isoformat())
    await tg_send(
        user_id,
        f"<b>Plan Extended</b>\n\nYour plan now runs until "
        f"<b>{new_expiry.strftime('%d %b %Y')}</b>.",
    )
    return {"ok": True, "expires_at": new_expiry.isoformat()}


async def message(user_id: int, text: str) -> dict:
    if not text.strip():
        return {"ok": False, "error": "empty message"}
    ok = await tg_send(user_id, text.strip(), parse_mode=None)
    return {"ok": ok}


async def broadcast(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        return {"ok": False, "error": "empty message"}
    db = settings.connect()
    try:
        ids = [r[0] for r in db.execute("SELECT user_id FROM clients")]
    finally:
        db.close()
    sent, failed = 0, 0
    for uid in ids:
        if await tg_send(uid, text, parse_mode=None):
            sent += 1
        else:
            failed += 1
        await asyncio.sleep(0.05)
    return {"ok": True, "sent": sent, "failed": failed}


def save_settings(demo_mode: bool | None, daily_amount: float | None) -> dict:
    db = settings.connect()
    try:
        if demo_mode is not None:
            db.execute(
                "INSERT INTO settings (key, value) VALUES ('demo_mode', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("true" if demo_mode else "false",),
            )
        if daily_amount is not None:
            if daily_amount <= 0:
                return {"ok": False, "error": "daily_amount must be positive"}
            db.execute(
                "INSERT INTO settings (key, value) VALUES ('daily_amount', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(daily_amount),),
            )
        db.commit()
    finally:
        db.close()
    return {"ok": True}
