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

    await bus.register(websocket, player_id, name, role)

    try:
        while True:
            raw = await websocket.receive_text()

            #akzeptiere sowohl plain "ping" als auch JSON ping
            if raw == "ping":
                await websocket.send_text("pong")
                await bus.touch(websocket)
                continue

            try:
                msg = json.loads(raw)
            except Exception:
                # unbekanntes Format, trotzdem als Aktivität werten
                await bus.touch(websocket)
                continue

            if msg.get("type") == "ping":
                await websocket.send_text("pong")
                await bus.touch(websocket)
                continue

            await bus.touch(websocket)
    except WebSocketDisconnect:
        await bus.unregister(websocket)
    except Exception:
        await bus.unregister(websocket)

