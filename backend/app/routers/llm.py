from fastapi import APIRouter
from app.base_models.llm_base_models import LLMRequest
from app.functions.llm.custom_model import run_custom_model
from fastapi.responses import StreamingResponse
from app.functions.embedding.embedding_model import embedding_search
from app.core import chat_store

router = APIRouter()

chat_history = []

@router.post("/runLLM")
async def run_llm(request: LLMRequest):
    chat_store.chat_history.append({"role": "user", "content": request.input_string})

    print(request.use_rulebook)
    # k has to be adjusted after some testing later.
    retrieved_docs = embedding_search(request.input_string, request.use_rulebook)
    context = "\n\n".join([doc.page_content for doc in retrieved_docs])


    chat_store.chat_history.insert(0, {
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
    })

    print(chat_store.chat_history)

    def event_generator():
        assistant_response = ""
        for chunk in run_custom_model(chat_store.chat_history):
            assistant_response += chunk
            yield f"{chunk}"
        # Append full assistant response to chat history after streaming
        chat_store.chat_history.append({"role": "assistant", "content": assistant_response})
        print(chat_store.chat_history)
        # Remove the context from chat history (first message)
        if chat_store.chat_history and chat_store.chat_history[0]["role"] == "system":
            del chat_store.chat_history[0]
        print(chat_store.chat_history)

    return StreamingResponse(event_generator(), media_type="text/plain")