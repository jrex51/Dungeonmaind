from uuid import UUID
from pydantic import BaseModel, Field

class ConfigRequest(BaseModel):
    player_id: UUID = Field(..., description="ID aus /players")
    selected_LLM: str = Field(..., description="User selected LLM")
    transcription_model: str = Field(..., description="Transcription model (base or medium)")
    embedding_model: str = Field(..., description="Embedding model")
    clear_chat: bool = Field(False, description="Whether to clear chat history")
    delete_transcriptions: bool = Field(False, description="Delete the transcirptions from the chroma_db")


class ConfigResponse(BaseModel):
    status: str = Field(..., description="Confirmation status")

