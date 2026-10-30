import asyncio
import json


class EventBus:
    def __init__(self):
        self._clients: set = set()
        self._lock = asyncio.Lock()

    async def add(self, ws):
        async with self._lock:
            self._clients.add(ws)

    async def remove(self, ws):
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, event: str, data: dict):
        payload = json.dumps({"event": event, "data": data or {}})
        async with self._lock:
            clients = list(self._clients)
        for ws in clients:
            try:
                await ws.send_text(payload)
            except Exception:
                try:
                    self._clients.discard(ws)
                except Exception:
                    pass


bus = EventBus()
