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

    def __init__(self, timeout_sec: int = 45):
        self._lock = asyncio.Lock()
        self._sockets: Set[WebSocket] = set()
        self._ws_meta: Dict[WebSocket, dict] = {}
        self._player_sockets: Dict[str, Set[WebSocket]] = {}  # player_id -> sockets | ein Player kann mehrere Tabs/Sockets offen haben, erst beim schließen des letzten einen leave ausführen
        self._pending_leave: Dict[str, asyncio.Task] = {}  # player_id -> task
        self._timeout_sec = timeout_sec
        self._gc_task: Optional[asyncio.Task] = None

    async def start(self):
        """startet den GarbageCollector-Loop"""
        # nur starten, wenn noch nicht gestartet
        if self._gc_task is None or self._gc_task.done():
            self._gc_task = asyncio.create_task(self._gc_loop())

    async def stop(self):
        """Stop GarbageCollector-Loop"""
        if self._gc_task is not None and not self._gc_task.done():
            self._gc_task.cancel()
            try:
                await self._gc_task
            except asyncio.CancelledError:
                pass
        self._gc_task = None
        # ausstehende Leave-Tasks abbrechen
        for t in self._pending_leave.values():
            t.cancel()
        self._pending_leave.clear()

    async def register(self, ws: WebSocket, player_id: str, name: str, role: str):
        """Neuen Socket registrieren und Join-Event broadcasten"""
        async with self._lock:
            self._sockets.add(ws)
            self._ws_meta[ws] = {
                "player_id": str(player_id),
                "name": name,
                "role": role,
                "last_seen": time.time(),
            }
            self._player_sockets.setdefault(str(player_id), set()).add(ws)
            # Falls ein Leave für diesen Spieler geplant war abbrechen
            task = self._pending_leave.pop(str(player_id), None)
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

    async def touch(self, ws: WebSocket):
        """Heartbeat vom Client - last_seen aktualisieren"""
        async with self._lock:
            if ws in self._ws_meta:
                self._ws_meta[ws]["last_seen"] = datetime.now(timezone.utc)

    async def publish(self, event: dict):
        """An alle verbundenen Sockets senden"""
        data = json.dumps(event, default=str)
        dead = []
        async with self._lock:
            targets = list(self._sockets)
        for ws in targets:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.unregister(ws)

    async def _gc_loop(self):
        """Räumt abgestürzte/pausierte Verbindungen anhand von last_seen auf"""
        try:
            while True:
                await asyncio.sleep(10)
                now = time.time()
                stale = []
                async with self._lock:
                    for ws, meta in list(self._ws_meta.items()):
                        if now - meta["last_seen"].timestamp() > self._timeout_sec:
                            stale.append(ws)
                for ws in stale:
                    await self.unregister(ws)
        except asyncio.CancelledError:
            return

    async def _backend_leave_and_publish(self, player_id: str):
        try:
            await store.group.deactivate(UUID(player_id), status=PlayerStatus.inactive)
        except Exception:
            # Wenn der Spieler schon weg ist, nicht hart abbrechen
            pass
        await self.publish({"type": "leave", "player_id": str(player_id)})

    async def kick(self, player_id: UUID):
        pid = str(player_id)
        sockets = list(self._player_sockets.get(pid, set()))
        for ws in sockets:
            try:
                await ws.close(code=4001, reason="kicked")
            except Exception:
                pass

    async def _server_leave_and_publish(self, player_id: str):
        # statt store.leave() jetzt "soft leave"
        store.group.deactivate(UUID(player_id), status=PlayerStatus.inactive)
        await self.publish({"type": "leave", "player_id": str(player_id)})

    def _silence_task_exception(t: asyncio.Task):
        try: _ = t.result()
        except Exception: pass

bus = PresenceBus()