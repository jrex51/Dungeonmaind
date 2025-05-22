from fastapi import APIRouter, HTTPException
from app.base_models.llm_base_models import LLMRequest, LLMResponse
from app.functions.llm.custom_model import run_custom_model

router = APIRouter()


@router.post("/runLLM", response_model=LLMResponse)
async def run_llm(request: LLMRequest):
    """
    Receives a prompt string, runs it through a custom model,
    and returns the generated text.
    """
    try:
        result = run_custom_model(request.input_string)
        return LLMResponse(output=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
