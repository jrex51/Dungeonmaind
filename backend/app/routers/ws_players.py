# live Update des frontends wenn sich etwas an der gruppe ändert
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.domain.models import Role
from app.core.bus import bus
from app.domain.models import PlayerStatus
from app.domain.store import store

router = APIRouter()

@router.websocket("/players")
async def ws_players(websocket: WebSocket, player_id: str = Query(...), name: str = Query(...), role: str = Query(...)):
    await websocket.accept()
    try:
        p = store.group.get_player(UUID(player_id))
        print(f"WS connect: {p.id} status={p.status} role={p.role}")

    except KeyError:
        await websocket.close(code=4004, reason="unknown player")
        return

    await bus.register(websocket, player_id, name, role)

    try:
        while True:
            await websocket.receive_text()
            await bus.touch(websocket)
    except WebSocketDisconnect:
        await bus.unregister(websocket)
    except Exception:
        await bus.unregister(websocket)

