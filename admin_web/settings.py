import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = os.environ.get("HIRE_DB_PATH") or str(
    (BASE_DIR.parent / "hire_bot" / "hire_bot.db").resolve()
)

ADMIN_USER = os.environ.get("ADMIN_USER", "anhaf")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "changeme")
JWT_SECRET = os.environ.get("JWT_SECRET", "change-this-secret")
INTERNAL_TOKEN = os.environ.get("ADMIN_WEB_TOKEN", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Mirrors hire_bot/config.py PLANS durations. Keep in sync.
PLAN_DAYS = {"daily": 1, "weekly": 7, "monthly": 30}
PLAN_LABELS = {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly"}
METHOD_LABELS = {
    "btc": "Bitcoin",
    "bep20": "USDT-BEP20",
    "trc20": "USDT-TRC20",
    "eth": "Ethereum",
    "erc20": "USDT-ERC20",
}


def connect() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=15000")
    except sqlite3.Error:
        pass
    return db
