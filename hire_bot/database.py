import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import aiosqlite

from config import PLANS

DB_PATH = os.environ.get("HIRE_DB_PATH") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "hire_bot.db"
)


@asynccontextmanager
async def _connect():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA busy_timeout=5000")
        yield db

CREATE_CLIENTS = """
CREATE TABLE IF NOT EXISTS clients (
    user_id             INTEGER PRIMARY KEY,
    username            TEXT,
    full_name           TEXT,
    plan                TEXT,
    method              TEXT,
    tx_id               TEXT,
    amount_usd          REAL,
    status              TEXT DEFAULT 'pending',
    auto_status         TEXT,
    hired_at            TEXT,
    expires_at          TEXT,
    reminded            INTEGER DEFAULT 0,
    demo                INTEGER DEFAULT 0,
    invoice_id          TEXT,
    network             TEXT,
    required_amount     TEXT,
    amount_paid_total   TEXT,
    invoice_created_at  TEXT,
    invoice_expires_at  TEXT,
    verify_status       TEXT,
    verify_code         TEXT,
    verify_message      TEXT
);
"""

CLIENT_COLUMNS = (
    "invoice_id", "network", "required_amount", "amount_paid_total",
    "invoice_created_at", "invoice_expires_at", "verify_status", "verify_code", "verify_message",
)

CREATE_SETTINGS = """
CREATE TABLE IF NOT EXISTS settings (
    key     TEXT PRIMARY KEY,
    value   TEXT
);
"""


async def init_db():
    async with _connect() as db:
        await db.execute(CREATE_CLIENTS)
        await db.execute(CREATE_SETTINGS)
        await db.commit()
        cursor = await db.execute("PRAGMA table_info(clients)")
        columns = {row[1] for row in await cursor.fetchall()}
        if "auto_status" not in columns:
            await db.execute("ALTER TABLE clients ADD COLUMN auto_status TEXT")
            await db.commit()
        for column in CLIENT_COLUMNS:
            if column not in columns:
                await db.execute(f"ALTER TABLE clients ADD COLUMN {column} TEXT")
                await db.commit()
        cursor = await db.execute("SELECT value FROM settings WHERE key = 'demo_mode'")
        row = await cursor.fetchone()
        if row is None:
            await db.execute("INSERT INTO settings (key, value) VALUES ('demo_mode', 'false')")
            await db.commit()
        cursor = await db.execute("SELECT value FROM settings WHERE key = 'daily_amount'")
        row = await cursor.fetchone()
        if row is None:
            await db.execute(
                "INSERT INTO settings (key, value) VALUES ('daily_amount', ?)",
                (str(PLANS["daily"]["amount"]),),
            )
            await db.commit()


async def get_client(user_id: int):
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM clients WHERE user_id = ?", (user_id,))
        return await cursor.fetchone()


async def upsert_client(**fields):
    keys = ", ".join(fields.keys())
    placeholders = ", ".join("?" for _ in fields)
    updates = ", ".join(f"{key} = excluded.{key}" for key in fields if key != "user_id")
    async with _connect() as db:
        await db.execute(
            f"INSERT INTO clients ({keys}) VALUES ({placeholders}) "
            f"ON CONFLICT(user_id) DO UPDATE SET {updates}",
            tuple(fields.values()),
        )
        await db.commit()


async def get_all_clients(status: str | None = None):
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        if status:
            cursor = await db.execute("SELECT * FROM clients WHERE status = ?", (status,))
        else:
            cursor = await db.execute("SELECT * FROM clients")
        return await cursor.fetchall()


async def get_pending():
    return await get_all_clients("pending")


async def get_awaiting_confirmation():
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM clients WHERE status = 'pending' AND auto_status = 'awaiting_confirmation'"
        )
        return await cursor.fetchall()


async def set_auto_status(user_id: int, auto_status: str | None):
    async with _connect() as db:
        await db.execute("UPDATE clients SET auto_status = ? WHERE user_id = ?", (auto_status, user_id))
        await db.commit()


async def get_active():
    return await get_all_clients("active")


async def set_status(user_id: int, status: str):
    async with _connect() as db:
        await db.execute("UPDATE clients SET status = ? WHERE user_id = ?", (status, user_id))
        await db.commit()


async def set_reminded(user_id: int):
    async with _connect() as db:
        await db.execute("UPDATE clients SET reminded = 1 WHERE user_id = ?", (user_id,))
        await db.commit()


async def set_expires_at(user_id: int, expires_at: str):
    async with _connect() as db:
        await db.execute("UPDATE clients SET expires_at = ? WHERE user_id = ?", (expires_at, user_id))
        await db.commit()


async def get_setting(key: str):
    async with _connect() as db:
        cursor = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return row[0] if row else None


async def set_setting(key: str, value: str):
    async with _connect() as db:
        await db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await db.commit()


async def get_daily_amount() -> float:
    value = await get_setting("daily_amount")
    return float(value) if value is not None else PLANS["daily"]["amount"]


async def set_daily_amount(amount: float):
    await set_setting("daily_amount", str(amount))


async def get_revenue_this_month():
    month_prefix = datetime.now(timezone.utc).strftime("%Y-%m")
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT COALESCE(SUM(amount_usd), 0) FROM clients "
            "WHERE status = 'active' AND hired_at LIKE ?",
            (f"{month_prefix}%",),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0
