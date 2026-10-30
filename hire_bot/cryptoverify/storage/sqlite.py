from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS consumed_txids (
    network TEXT NOT NULL,
    txid TEXT NOT NULL,
    invoice_id TEXT NOT NULL,
    claimed_at REAL NOT NULL,
    UNIQUE (network, txid)
);
CREATE TABLE IF NOT EXISTS verified_results (
    invoice_id TEXT NOT NULL,
    network TEXT NOT NULL,
    txid TEXT NOT NULL,
    payload TEXT NOT NULL,
    expires_at REAL NOT NULL,
    UNIQUE (invoice_id, network, txid)
);
CREATE TABLE IF NOT EXISTS invoice_tips (
    invoice_id TEXT NOT NULL,
    network TEXT NOT NULL,
    height INTEGER NOT NULL,
    UNIQUE (invoice_id, network)
);
CREATE TABLE IF NOT EXISTS invoice_quotes (
    invoice_id TEXT NOT NULL, network TEXT NOT NULL, payload TEXT NOT NULL,
    UNIQUE (invoice_id, network)
);
CREATE TABLE IF NOT EXISTS invoice_payments (
    invoice_id TEXT NOT NULL, network TEXT NOT NULL, txid TEXT NOT NULL,
    amount TEXT NOT NULL, paid_at REAL NOT NULL,
    UNIQUE (invoice_id, network, txid)
);
"""


class SQLiteStorage:
    def __init__(self, file_path: str = "cryptoverify.db") -> None:
        self.file_path = file_path
        self._lock = asyncio.Lock()
        self._connection: sqlite3.Connection | None = None

    def _open(self) -> sqlite3.Connection:
        if self._connection is None:
            if self.file_path != ":memory:":
                Path(self.file_path).parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(self.file_path, check_same_thread=False, isolation_level=None)
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA busy_timeout=5000")
            self._connection.executescript(SCHEMA)
        return self._connection

    async def _run(self, work: Any) -> Any:
        async with self._lock:
            return await asyncio.to_thread(work)

    async def prepare(self) -> None:
        await self._run(self._open)

    async def claim_txid(self, network: str, txid: str, invoice_id: str) -> str | None:
        def work() -> str | None:
            connection = self._open()
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT invoice_id FROM consumed_txids WHERE network = ? AND txid = ?", (network, txid)
                ).fetchone()
                if row is not None:
                    connection.execute("COMMIT")
                    return None if row[0] == invoice_id else str(row[0])
                connection.execute(
                    "INSERT INTO consumed_txids (network, txid, invoice_id, claimed_at) VALUES (?, ?, ?, ?)",
                    (network, txid, invoice_id, time.time()),
                )
                connection.execute("COMMIT")
                return None
            except sqlite3.IntegrityError:
                connection.execute("ROLLBACK")
                row = connection.execute(
                    "SELECT invoice_id FROM consumed_txids WHERE network = ? AND txid = ?", (network, txid)
                ).fetchone()
                if row is None or row[0] == invoice_id:
                    return None
                return str(row[0])
            except Exception:
                connection.execute("ROLLBACK")
                raise

        return await self._run(work)

    async def owner_of_txid(self, network: str, txid: str) -> str | None:
        def work() -> str | None:
            row = self._open().execute(
                "SELECT invoice_id FROM consumed_txids WHERE network = ? AND txid = ?", (network, txid)
            ).fetchone()
            return str(row[0]) if row else None

        return await self._run(work)

    async def remember_result(self, invoice_id: str, network: str, txid: str, payload: dict[str, Any], ttl_seconds: int) -> None:
        def work() -> None:
            self._open().execute(
                "INSERT OR REPLACE INTO verified_results (invoice_id, network, txid, payload, expires_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (invoice_id, network, txid, json.dumps(payload), time.time() + ttl_seconds),
            )

        await self._run(work)

    async def recall_result(self, invoice_id: str, network: str, txid: str) -> dict[str, Any] | None:
        def work() -> dict[str, Any] | None:
            connection = self._open()
            row = connection.execute(
                "SELECT payload, expires_at FROM verified_results WHERE invoice_id = ? AND network = ? AND txid = ?",
                (invoice_id, network, txid),
            ).fetchone()
            if row is None:
                return None
            if float(row[1]) < time.time():
                connection.execute(
                    "DELETE FROM verified_results WHERE invoice_id = ? AND network = ? AND txid = ?",
                    (invoice_id, network, txid),
                )
                return None
            return json.loads(row[0])

        return await self._run(work)

    async def remember_invoice_tip(self, invoice_id: str, network: str, height: int) -> None:
        def work() -> None:
            self._open().execute(
                "INSERT OR IGNORE INTO invoice_tips (invoice_id, network, height) VALUES (?, ?, ?)",
                (invoice_id, network, height),
            )

        await self._run(work)

    async def recall_invoice_tip(self, invoice_id: str, network: str) -> int | None:
        def work() -> int | None:
            row = self._open().execute(
                "SELECT height FROM invoice_tips WHERE invoice_id = ? AND network = ?", (invoice_id, network)
            ).fetchone()
            return int(row[0]) if row else None

        return await self._run(work)

    async def remember_invoice_quote(self, invoice_id: str, network: str, payload: dict[str, Any]) -> None:
        def work() -> None:
            self._open().execute(
                "INSERT OR IGNORE INTO invoice_quotes (invoice_id, network, payload) VALUES (?, ?, ?)",
                (invoice_id, network, json.dumps(payload)),
            )

        await self._run(work)

    async def recall_invoice_quote(self, invoice_id: str, network: str) -> dict[str, Any] | None:
        def work() -> dict[str, Any] | None:
            row = self._open().execute(
                "SELECT payload FROM invoice_quotes WHERE invoice_id = ? AND network = ?", (invoice_id, network)
            ).fetchone()
            return json.loads(row[0]) if row else None

        return await self._run(work)

    async def remember_invoice_payment(self, invoice_id: str, network: str, txid: str, amount: str) -> None:
        def work() -> None:
            self._open().execute(
                "INSERT OR IGNORE INTO invoice_payments (invoice_id, network, txid, amount, paid_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (invoice_id, network, txid, amount, time.time()),
            )

        await self._run(work)

    async def recall_invoice_payments(self, invoice_id: str, network: str) -> list[tuple[str, str]]:
        def work() -> list[tuple[str, str]]:
            rows = self._open().execute(
                "SELECT txid, amount FROM invoice_payments WHERE invoice_id = ? AND network = ? ORDER BY paid_at",
                (invoice_id, network),
            ).fetchall()
            return [(str(row[0]), str(row[1])) for row in rows]

        return await self._run(work)

    async def close(self) -> None:
        def work() -> None:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

        await self._run(work)
