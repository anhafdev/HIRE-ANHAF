from __future__ import annotations

from .base import StorageBackend
from .memory import MemoryStorage
from .sqlite import SQLiteStorage


def build_storage(url: str) -> StorageBackend:
    address = (url or "").strip()
    if not address or address.startswith("memory"):
        return MemoryStorage()
    if address.startswith("sqlite"):
        path = address.split("://", 1)[1] if "://" in address else address
        if path.startswith("/"):
            path = path[1:]
        return SQLiteStorage(path or "cryptoverify.db")
    if address.startswith("redis"):
        from .redis_store import RedisStorage

        return RedisStorage(address)
    return SQLiteStorage(address)


__all__ = ["StorageBackend", "MemoryStorage", "SQLiteStorage", "build_storage"]
