from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    secret_key: str = "change-me-in-production-use-a-long-random-string"
    access_token_expire_minutes: int = 480
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    database_url: str = "postgresql+asyncpg://support:support@localhost:5432/support"
    database_url_sync: str = "postgresql+psycopg2://support:support@localhost:5432/support"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    seed_agent_email: str = "agent@example.com"
    seed_agent_password: str = "agent123!"

    # Knowledge / embeddings + Gemini LLM (Day 2)
    gemini_api_key: str = ""
    embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 1536
    chunk_size_tokens: int = 600
    chunk_overlap_tokens: int = 80
    knowledge_top_k: int = 5
    llm_model: str = "gemini-3.1-flash-lite"
    knowledge_upload_dir: str = "/tmp/support-knowledge"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def has_gemini(self) -> bool:
        return bool(self.gemini_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
