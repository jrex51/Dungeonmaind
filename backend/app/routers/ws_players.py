# live Update des frontends wenn sich etwas an der gruppe ändert

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.bus import bus

router = APIRouter()

@router.websocket("/players")
async def ws_players(websocket: WebSocket):
    await websocket.accept()
    await bus.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await bus.disconnect(websocket)

