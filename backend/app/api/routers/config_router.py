from fastapi import APIRouter, HTTPException, status
import asyncio
from app.base_models.config_base_models import ConfigRequest, ConfigChangeResponse, ConfigGetResponse
from app.core.config import settings
from app.core.chat_store import chat_store
from app.domain.store import store
from app.functions.embedding.embedding_model import delete_transcription_embeddings, reembed_chroma_entries
from app.functions.process_audio_data.transcribe_audio import reload_transcription_model
from app.functions.geographic_mapping.session_integration import clear_views, get_lifecycle


router = APIRouter()

VALID_MODELS = {
    "hf.co/bartowski/microsoft_Phi-4-mini-instruct-GGUF:Q5_K_M",
    "hf.co/bartowski/google_gemma-3-1b-it-qat-GGUF:Q5_K_M",
    "hf.co/bartowski/google_gemma-3-12b-it-qat-GGUF:Q5_K_M",
    "hf.co/bartowski/mistralai_Ministral-3-14B-Instruct-2512-GGUF:Q5_K_M",
    "hf.co/bartowski/mistralai_Ministral-3-3B-Instruct-2512-GGUF:Q5_K_M"
}

VALID_TRANS_MODELS = {"base", "medium", "large-v3"}

VALID_EMBEDDING_MODELS = {
    "all-MiniLM-L6-v2",
    "all-MiniLM-L12-v2",
    "paraphrase-multilingual-MiniLM-L12-v2"
}

VALID_EMBEDDING_Top_K = {3, 6, 9, 12}

@router.post("/changeConfig", response_model=ConfigChangeResponse)
async def change_config(request: ConfigRequest):
    """Receives a selected config option and returns confirmation."""
    return await get_lifecycle().run(lambda: _change_config(request))


async def _change_config(request: ConfigRequest):
    try:
        if request.selected_LLM not in VALID_MODELS:
            raise HTTPException(status_code=400, detail="Invalid llm model selected.")
        if request.transcription_model not in VALID_TRANS_MODELS:
            raise HTTPException(status_code=400, detail="Invalid transcription model selected.")
        if request.embedding_model not in VALID_EMBEDDING_MODELS:
            raise HTTPException(status_code=400, detail="Invalid embedding model selected.")
        if request.embedding_top_k not in VALID_EMBEDDING_Top_K:
            raise HTTPException(status_code=400, detail="Invalid embedding TopK selected.")

        # save in config
        if settings.llm_model != request.selected_LLM:
            settings.llm_model = request.selected_LLM
            print(f"[CONFIG] LLM changed to: {settings.llm_model}")

        if settings.transcription_model != request.transcription_model:
            settings.transcription_model = request.transcription_model
            reload_transcription_model()
            print(f"[CONFIG] Transcription model changed to: {settings.transcription_model}")

        if request.clear_chat:
            try:
                player = store.group.get_player(request.player_id)
            except KeyError:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Player not found")
            await chat_store.clear_all()
            print("[CONFIG] Chat Verlauf gelöscht.")

        if request.delete_transcriptions:
            await asyncio.to_thread(clear_views)
            await asyncio.to_thread(delete_transcription_embeddings)
            print("[CONFIG] Embedded transcriptions deleted")

        if settings.embedding_model != request.embedding_model:
            # Rebuilding the database can also fail after partial mutation.
            await asyncio.to_thread(clear_views)
            await asyncio.to_thread(reembed_chroma_entries, request.embedding_model)
            settings.embedding_model = request.embedding_model
            print(f"[CONFIG] Embedding model changed to: {settings.embedding_model}")

        if settings.embedding_top_k != request.embedding_top_k:
            settings.embedding_top_k = request.embedding_top_k
            print(f"[CONFIG] Embedding TopK changed to: {settings.embedding_top_k}")


        return ConfigChangeResponse(status="success")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/getConfig", response_model=ConfigGetResponse)
async def get_config():
    return ConfigGetResponse(
        selected_LLM=settings.llm_model,
        transcription_model=settings.transcription_model,
        embedding_model=settings.embedding_model,
        embedding_top_k=settings.embedding_top_k
    )

