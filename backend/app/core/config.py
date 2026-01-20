import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", case_sensitive=False)
    app_name: str = Field(
        default="Awesome API",
        validation_alias="APP_NAME",
        description="Name of the application"
    )
    debug: bool = Field(
        default=False,
        validation_alias="DEBUG",
        description="Enable debug logging"
    )
    host: str = Field(
        default="0.0.0.0",
        validation_alias="HOST",
        description="Bind address"
    )
    port: int = Field(
        default=8000,
        validation_alias="PORT",
        description="Listening port"
    )

    hf_token: str | None = Field(
        default=None,
        alias="HF_TOKEN",
        description="Hugging Face access token"
    )

    llm_model: str = Field(
        default="hf.co/bartowski/microsoft_Phi-4-mini-instruct-GGUF:Q5_K_M",
        validation_alias="LLM_MODEL",
        description="The default LLM model used by the backend"
    )

    transcription_model: str = Field(
        default="base",
        validation_alias="TRANSCRIPTION_MODEL",
        description="Transcription model (base or medium)"
    )

    embedding_model: str = Field(
        default="all-MiniLM-L6-v2",
        validation_alias="EMBEDDING_MODEL",
        description="Embedding model"
    )

    embedding_top_k: int = Field(
        default=4,
        validation_alias="EMBEDDING_TOP_K",
        description="Number of top_k embeddings (2-8)"
    )

    backend_root_path: str = Field(
        default_factory=lambda: os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        description="Root directory of the backend"
    )

    #@property
    #def chroma_db_path(self) -> str:
    #    return os.path.join(self.backend_root_path, "data", "chroma_db")

    _chroma_db_path: str | None = None

    @property
    def chroma_db_path(self) -> str:
        # If a custom path was set, return it; otherwise return default
        return self._chroma_db_path or os.path.join(self.backend_root_path, "data", "chroma_db")

    @chroma_db_path.setter
    def chroma_db_path(self, value: str):
        self._chroma_db_path = value


settings = Settings()