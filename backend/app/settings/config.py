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


settings = Settings()