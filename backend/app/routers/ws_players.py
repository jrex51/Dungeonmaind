# live Update des frontends wenn sich etwas an der gruppe ändert

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.core.bus import bus

router = APIRouter()

@router.websocket("/players")
async def ws_players(websocket: WebSocket, player_id: str = Query(...), name: str = Query(...), role: str = Query(...)):
    await websocket.accept()
    await bus.register(websocket, player_id, name, role)
    try:
        while True:
            await websocket.receive_text()
            await bus.touch(websocket)
    except WebSocketDisconnect:
        await bus.unregister(websocket)
    except Exception:
        await bus.unregister(websocket)

