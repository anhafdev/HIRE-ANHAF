"""Fire-and-forget events from the bot to the admin dashboard.

No-op unless ADMIN_WEB_URL + ADMIN_WEB_TOKEN are set. Never raises —
the bot must keep working even if the dashboard is down.
"""

import asyncio
import logging
import os

logger = logging.getLogger(__name__)


def push(event: str, payload: dict | None = None):
    url = os.environ.get("ADMIN_WEB_URL", "").rstrip("/")
    token = os.environ.get("ADMIN_WEB_TOKEN", "")
    if not url or not token:
        return
    try:
        import httpx
    except ImportError:
        return

    async def _send():
        try:
            async with httpx.AsyncClient(timeout=4) as client:
                await client.post(
                    f"{url}/api/internal/event",
                    json={"event": event, "data": payload or {}},
                    headers={"X-Internal-Token": token},
                )
        except Exception:
            logger.debug("dashboard event %s failed", event, exc_info=True)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    asyncio.create_task(_send())
