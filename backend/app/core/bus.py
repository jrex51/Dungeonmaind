# Methode um das frontend bei Updates im Backend zu aktualisieren (vor allem, wenn sich gruppenmitglieder ändern)

import asyncio, json

from app.base_models.schemas import PlayerIn


class PlayerBus:
    def __init__(self):
        self._clients = set()  # verbundene WebSockets
        self._lock = asyncio.Lock()

    async def connect(self, ws):
        async with self._lock:
            self._clients.add(ws)

    async def disconnect(self, ws):
        async with self._lock:
            self._clients.discard(ws)

    async def publish(self, event: dict):
        data = json.dumps(event, default=str)
        dead = []
        for ws in list(self._clients):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)

bus = PlayerBus()