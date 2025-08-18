from fastapi import APIRouter, HTTPException
from app.base_models.config_base_models import ConfigRequest, ConfigResponse
from app.core.config import settings
from app.core import chat_store

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
        settings.transcription_model = request.transcription_model
        print(f"[CONFIG] Modell geändert auf: {settings.llm_model}")
        print(f"[CONFIG] Transkriptionsmodell geändert auf: {settings.transcription_model}")

        if request.clear_chat:
            chat_store.chat_history.clear()
            print("[CHAT] Verlauf gelöscht.")

        return ConfigResponse(status="success")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))