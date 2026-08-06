# live Update des frontends wenn sich etwas an der gruppe ändert
import json
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.domain.models import Role
from app.core.bus import bus
from app.domain.models import PlayerStatus
from app.domain.store import store

router = APIRouter()

@router.websocket("/players")
async def ws_players(websocket: WebSocket, player_id: UUID = Query(...), name: str = Query(...), role: str = Query(...)):
    await websocket.accept()
    try:
        p = store.group.get_player(player_id)
        print(f"WS connect: {p.id} status={p.status} role={p.role}")
    except ValueError:
        await websocket.close(code=4004, reason="invalid player_id")
        return
    except KeyError:
        await websocket.close(code=4004, reason="unknown player")
        return

    await bus.register(websocket, str(player_id), name, role)

    try:
        while True:
            # blockiert bis client etwas sendet oder disconnect passiert
            await websocket.receive_text()
    except WebSocketDisconnect:
        await bus.unregister(websocket)
    except Exception:
        await bus.unregister(websocket)

