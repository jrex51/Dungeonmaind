from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
import os
from app.base_models.llm_base_models import LLMRequest
from app.functions.llm.custom_model import run_custom_model
from app.functions.llm.system_prompt import get_system_prompt
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

    # 3) Embeddings erhalten für system prompt
    # k has to be adjusted after some testing later.
    retrieved_docs = embedding_search(req.input_string, req.use_rulebook)

    await chat_store.append(player.id, "user", req.input_string)

    context = ""
    sources = [doc.metadata.get("source") for doc in retrieved_docs]
    for doc in retrieved_docs:
        context += "--Source-- " + doc.metadata.get("source") + "--End Source-- \n"
        if doc.metadata.get("path") is not "none":
            full_path = doc.metadata.get("path")
            filename = os.path.basename(full_path).replace(".md", "")
            context += "-filename-" + filename + "-End filename- \n"
        context += doc.page_content + "\n\n"


    #context = "\n\n".join([doc.page_content for doc in retrieved_docs])
    system_message = get_system_prompt(context)

    # 4) Generator zum Streamen
    async def event_generator(system_prompt: str):
        #yield json.dumps({"type": "metadata", "markdown_texts": markdown_texts}) + "\n"

        llm_resp = ""
        # komplette History
        history = await chat_store.history(player.id)
        history.insert(0, system_prompt)
        print(history)
        async for chunk in run_custom_model(history):
            llm_resp += chunk
            yield chunk
            #yield json.dumps({"type": "llm_chunk", "content": chunk}) + "\n"
        # 4) Antwort speichern
        print(llm_resp)
        await chat_store.append(player.id, "assistent", llm_resp)

    return StreamingResponse(event_generator(system_message), media_type="text/plain")