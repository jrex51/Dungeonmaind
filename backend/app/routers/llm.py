from fastapi import APIRouter, HTTPException, status
from app.base_models.llm_base_models import LLMRequest
from app.functions.llm.custom_model import run_custom_model
from fastapi.responses import StreamingResponse
from app.core.chat_store import chat_store
from app.domain.store import store

router = APIRouter()

@router.post("/run", response_class=StreamingResponse)
async def run_llm(req: LLMRequest):
    # 1) Spieler existiert?
    try:
        print(f"versuche Spieler ID zu bekommen + {req.player_id}")
        print(f"group size: {store.group.size()}")
        player = store.group.get_player(req.player_id)
    except KeyError:
        print("hat nicht geklappt")
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Player not found")

    # 2) Nachricht speichern
    print("speichere nachricht")
    await chat_store.append(player.id, "user", req.input_string)

    # 3) Generator zum Streamen
    async def event_generator():
        llm_resp = ""
        # komplette History
        history = await chat_store.history(player.id)
        print(isinstance(history, dict))
        for chunk in run_custom_model(history):
            llm_resp += chunk
            yield chunk
        # 4) Antwort speichern
        await chat_store.append(player.id, "assistent", llm_resp)

    return StreamingResponse(event_generator(), media_type="text/plain")