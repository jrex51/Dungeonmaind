from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from app.base_models.llm_base_models import LLMRequest
from app.functions.llm.custom_model import run_custom_model
from app.core.chat_store import chat_store
from app.domain.store import store
from app.functions.embedding.embedding_model import embedding_search


router = APIRouter()

@router.post("/run", response_class=StreamingResponse)
async def run_llm(req: LLMRequest):
    # 1) Spieler existiert?
    try:
        print(f"trying to get player ID + {req.player_id}")
        print(f"group size: {store.group.size()}")
        player = store.group.get_player(req.player_id)
    except KeyError:
        print("Player not found")
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Player not found")

    # 2) Nachricht speichern
    print("speichere nachricht")
    await chat_store.append(player.id, "user", req.input_string)

    # 3) Embeddings erhalten für system prompt
    # k has to be adjusted after some testing later.
    retrieved_docs = embedding_search(req.input_string, req.use_rulebook)
    context = "\n\n".join([doc.page_content for doc in retrieved_docs])

    system_message = {
        "role": "system",
        "content": (
            f"IMPORTANT: You are a LLM, which helps a group of players to play the roleplay game Dungeons and Dragons. "
            f"The users might ask you about the rules of the game or content of past sessions. "
            f"For this you will be provided a context, from a database. "
            f"Your answers should always be based on this context, even if the user does not specify that the answer should be based on the context. "
            f"Only Questions non Dungeons and Dragons related might be answered without using the provided context.\n\n"
            f"--- Begin of context --- \n\n"
            f"Use the following retrieved context to help answer the users question:\n\n"
            f"{context}\n\n"
            f"--- End of context ---"
        )
    }

    # 4) Generator zum Streamen
    async def event_generator(system_prompt: str):
        llm_resp = ""
        # komplette History
        history = await chat_store.history(player.id)
        history.insert(0, system_prompt)
        print(history)
        async for chunk in run_custom_model(history):
            llm_resp += chunk
            yield chunk
        # 4) Antwort speichern
        print(llm_resp)
        await chat_store.append(player.id, "assistent", llm_resp)

    return StreamingResponse(event_generator(system_message), media_type="text/plain")