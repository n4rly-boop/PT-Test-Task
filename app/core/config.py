from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="PT-LLM-Assistant", alias="APP_NAME")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")

    # Model configuration
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_base_url: str = Field(default="", alias="LLM_BASE_URL")
    llm_model: str = Field(default="google/gemini-2.5-flash-preview-09-2025", alias="LLM_MODEL")
    llm_error_code: str = Field(default="", alias="LLM_ERROR_CODE")

    # Database configuration
    db_url: str = Field(default="postgresql+psycopg://postgres:postgres@db:5432/db", alias="DATABASE_URL")

    # Embedding configuration
    embedding_model: str = Field(default="BAAI/bge-m3", alias="EMBEDDING_MODEL")
    embedding_dim: int = Field(default=1024, alias="EMBEDDING_DIM")

    # Chat configuration
    chat_history_length: int = Field(default=50, alias="CHAT_HISTORY_LENGTH")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()