from fastapi import APIRouter, HTTPException
from app.base_models.llm_base_models import LLMRequest, LLMResponse
from app.functions.llm.custom_model import run_custom_model

router = APIRouter()

# Global chat history list (simple example, resets on app restart)
chat_history = []

@router.post("/runLLM", response_model=LLMResponse)
async def run_llm(request: LLMRequest):
    """
    Receives a prompt string, runs it through a custom model,
    and returns the generated text.
    """
    try:
        # Append new message to chat history
        chat_history.append({"role": "user", "content": request.input_string})

        # Complete chat history + current prompt is given to the model
        result = run_custom_model(chat_history)

        # Append assistant response to chat history
        chat_history.append({"role": "assistant", "content": result})

        print(chat_history)

        return LLMResponse(output=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))