from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
import os
from app.base_models.llm_base_models import LLMRequest
from app.functions.llm.custom_model import run_custom_model
from app.functions.llm.system_prompt import get_system_prompt
from app.core.chat_store import chat_store
from app.domain.store import store
from app.functions.embedding.embedding_model import embedding_search, embed_text, embedding_search_on_chat_history
from app.functions.embedding.markdown_reader import read_markdown_file
from app.core.config import settings


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
    retrieved_docs = embedding_search(req.input_string, req.use_rulebook)

    embedded_request = embed_text(req.input_string)
    top_k_chat_history = await embedding_search_on_chat_history(req.input_string, embedded_request, player.id)

    # Maybe move this to the end
    await chat_store.append(player.id, "user", req.input_string, embedded_request)

    context = ""
    # sources = [doc.metadata.get("source") for doc in retrieved_docs]
    for doc in retrieved_docs:
        context += "--Source-- " + doc.metadata.get("source") + "--End Source-- \n"
        if doc.metadata.get("path") is not None:
            full_path = doc.metadata.get("path")
            filename = os.path.basename(full_path).replace(".md", "")
            context += "-filename-" + filename + "-End filename- \n"
        context += doc.page_content + "\n\n"


    #context = "\n\n".join([doc.page_content for doc in retrieved_docs])
    system_message = get_system_prompt(context)

    # 4) Generator zum Streamen
    async def event_generator(system_prompt: dict, chat_history: list[dict]):
        #yield json.dumps({"type": "metadata", "markdown_texts": markdown_texts}) + "\n"

        llm_resp = ""
        # komplette History
        history = await chat_store.history(player.id)
        chat_history.insert(0, system_prompt)
        #print("----------")
        print(chat_history)
        async for chunk in run_custom_model(chat_history):
            llm_resp += chunk
            yield chunk
            #yield json.dumps({"type": "llm_chunk", "content": chunk}) + "\n"
        # 4) Antwort speichern
        print(llm_resp)
        embedded_response = embed_text(llm_resp)
        await chat_store.append(player.id, "assistant", llm_resp, embedded_response)

    return StreamingResponse(event_generator(system_message, top_k_chat_history), media_type="text/plain")
