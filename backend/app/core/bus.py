import asyncio, json, time
from datetime import datetime, timezone
from typing import Dict, Set, Optional
from fastapi import WebSocket
from uuid import UUID

from app.domain.models import PlayerStatus
from app.domain.store import store

GRACE_SEC = 2  # Reload-Toleranz

class PresenceBus:
    """
    Präsenzverwaltung die einzelnen frontends/Spieler:
    - register/unregister verknüpft WebSocket mit player_id
    - touch aktualisiert last_seen (Heartbeat)
    - broadcast_all sendet an alle verbundenen Sockets
    - publish bleibt als Alias auf broadcast_all
    - GC entfernt stale Verbindungen (Fallback)
    """

    def __init__(self, timeout_sec: int = 60):
        self._lock = asyncio.Lock()
        self._sockets: Set[WebSocket] = set()
        self._ws_meta: Dict[WebSocket, dict] = {}  # ws -> {"player_id": "..."}
        self._player_sockets: Dict[str, Set[WebSocket]] = {}  # player_id -> set(ws) | ein Player kann mehrere Tabs/Sockets offen haben, erst beim schließen des letzten einen leave ausführen
        self._pending_leave: Dict[str, asyncio.Task] = {}  # player_id -> task

    async def register(self, ws: WebSocket, player_id: str, name: str, role: str):
        """Neuen Socket registrieren und Join-Event broadcasten"""
        async with self._lock:
            pid = str(player_id)
            self._sockets.add(ws)
            self._ws_meta[ws] = {
                "player_id": pid,
                "name": name,
                "role": role,
                "last_seen": time.time(),
            }
            self._player_sockets.setdefault(pid, set()).add(ws)
            # Falls ein Leave für diesen Spieler geplant war abbrechen
            task = self._pending_leave.pop(pid, None)
            if task and not task.done():
                task.cancel()
                #task.add_done_callback(_silence_task_exception)

    async def unregister(self, ws: WebSocket):
        """Socket abmelden und Leave-Event broadcasten"""
        meta = None
        last_socket_for_player = False

        async with self._lock:
            meta = self._ws_meta.pop(ws, None)
            self._sockets.discard(ws)
            if meta:
                pid = meta["player_id"]
                s = self._player_sockets.get(pid)
                if s:
                    s.discard(ws)
                    if not s:
                        # Letzter Socket dieses Spielers
                        self._player_sockets.pop(pid, None)
                        last_socket_for_player = True
        try:
            await ws.close()
        except Exception:
            pass

        if not meta:
            return

        player_id = meta["player_id"]

        # Wenn noch andere Tabs dieses Spielers offen sind, nichts tun
        if not last_socket_for_player:
            return

        # letzter Socket weg -> Leave planen
        async def delayed_leave(pid: str):
            try:
                await asyncio.sleep(GRACE_SEC)
                async with self._lock:
                    still_zero = pid not in self._player_sockets or not self._player_sockets.get(pid)
                if still_zero:
                    await self._backend_leave_and_publish(pid)
            except asyncio.CancelledError:
                return
            finally:
                # noinspection PyAsyncCall
                self._pending_leave.pop(pid, None)  # durch await wird Exception geworfen, deswegen unterdrückt

        task = asyncio.create_task(delayed_leave(player_id))
        #task.add_done_callback(_silence_task_exception)
        async with self._lock:
            # Falls es schon einen Task gibt, ersetzen
            old = self._pending_leave.get(player_id)
            if old and not old.done():
                old.cancel()
                #old.add_done_callback(_silence_task_exception)
            self._pending_leave[player_id] = task

    async def publish(self, event: dict):
        """An alle verbundenen Sockets senden"""
        data = json.dumps(event, default=str)
        dead: list[WebSocket] = []
        async with self._lock:
            targets = list(self._sockets)
        for ws in targets:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.unregister(ws)

    async def _backend_leave_and_publish(self, player_id: str):
        try:
            await store.group.deactivate(UUID(player_id), status=PlayerStatus.inactive)
        except Exception:
            # Wenn der Spieler schon weg ist, nicht hart abbrechen
            pass
        await self.publish({"type": "leave", "player_id": str(player_id)})

    async def kick(self, player_id: UUID):
        pid = str(player_id)
        async with self._lock:
            sockets = list(self._player_sockets.get(pid, set()))
        for ws in sockets:
            try:
                await ws.close(code=4001, reason="kicked")
            except Exception:
                pass

bus = PresenceBus()