from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    OPENAI_API_KEY: str = ""
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_STORAGE_BUCKET: str = "documents"
    DATABASE_URL: str | None = None
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "intellidocs"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    MAX_UPLOAD_BYTES: int = 15 * 1024 * 1024
    MAX_PAGES_PER_DOCUMENT: int = 500
    TRIAL_MAX_DOCUMENTS: int = 25
    TRIAL_MAX_STORAGE_BYTES: int = 50 * 1024 * 1024
    TRIAL_MAX_PAGES_PER_MONTH: int = 500
    TRIAL_MAX_QUESTIONS_PER_MONTH: int = 100
    PRO_MAX_DOCUMENTS: int = 250
    PRO_MAX_STORAGE_BYTES: int = 2 * 1024 * 1024 * 1024
    PRO_MAX_PAGES_PER_MONTH: int = 5000
    PRO_MAX_QUESTIONS_PER_MONTH: int = 2000
    PROCESSING_STALE_AFTER_SECONDS: int = 60 * 60
    # Standard USD rates per million tokens; historical records keep a snapshot.
    AI_GPT5_INPUT_RATE: float = 1.25
    AI_GPT5_CACHED_INPUT_RATE: float = 0.125
    AI_GPT5_OUTPUT_RATE: float = 10.0
    AI_GPT5_MINI_INPUT_RATE: float = 0.25
    AI_GPT5_MINI_CACHED_INPUT_RATE: float = 0.025
    AI_GPT5_MINI_OUTPUT_RATE: float = 2.0
    AI_EMBEDDING_INPUT_RATE: float = 0.02
    RAG_TOP_K: int = 10
    FRONTEND_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def frontend_origins(self) -> list[str]:
        return [
            origin.strip().rstrip("/")
            for origin in self.FRONTEND_ORIGINS.split(",")
            if origin.strip()
        ]

    model_config = SettingsConfigDict(
        env_file=(
            Path(__file__).resolve().parent.parent
            / ".env",
            Path(__file__).resolve().parents[2]
            / ".env",
        ),
        extra="ignore",
    )


settings = Settings()
