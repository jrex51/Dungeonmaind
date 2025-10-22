from fastapi import APIRouter, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from app.base_models.config_base_models import ConfigRequest, ConfigResponse
from app.core.config import settings
from app.core.chat_store import chat_store
from app.domain.store import store

from app.functions.process_audio_data.transcribe_audio import reload_transcription_model


router = APIRouter()

VALID_MODELS = {
    "hf.co/bartowski/microsoft_Phi-4-mini-instruct-GGUF:Q5_K_M",
    "hf.co/bartowski/Qwen_Qwen3-1.7B-GGUF:Q5_K_M",
    "hf.co/bartowski/google_gemma-3-1b-it-qat-GGUF:Q5_K_M",
    "hf.co/bartowski/google_gemma-3-12b-it-qat-GGUF:Q5_K_M"
}

VALID_TRANS_MODELS = {"base", "medium"}

@router.post("/changeConfig", response_model=ConfigResponse)
async def submit_config(request: ConfigRequest):
    """
    Receives a selected config option and returns confirmation.
    """
    try:
        if request.selected_LLM not in VALID_MODELS:
            raise HTTPException(status_code=400, detail="Invalid llm model selected.")
        if request.transcription_model not in VALID_TRANS_MODELS:
            raise HTTPException(status_code=400, detail="Invalid transcription model selected.")

        # save in config
        settings.llm_model = request.selected_LLM
        print(f"[CONFIG] LLM Modell geändert auf: {settings.llm_model}")

        prev_trans = settings.transcription_model
        if request.transcription_model != prev_trans:
            settings.transcription_model = request.transcription_model
            print(f"[CONFIG] Transkriptionsmodell geändert zu: {settings.transcription_model}. Wird neu geladen...")

            try:
                await run_in_threadpool(reload_transcription_model)
            except RuntimeError as e:
                settings.transcription_model = prev_trans
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                    detail=f"Failed to load transcription model: {e}")
        else:
            print(f"[CONFIG] Transkriptionsmodell unverändert: {settings.transcription_model}")

        if request.clear_chat:
            try:
                player = store.group.get_player(request.player_id)
            except KeyError:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Player not found")
            await chat_store.clear(player.id)
            print("[CHAT] Verlauf gelöscht.")

        return ConfigResponse(status="success")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))