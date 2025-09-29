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

    backend_root_path: str = Field(
        default_factory=lambda: os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        description="Root directory of the backend"
    )

    @property
    def chroma_db_path(self) -> str:
        return os.path.join(self.backend_root_path, "data", "chroma_db")


settings = Settings()