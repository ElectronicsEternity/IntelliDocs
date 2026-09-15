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
    MAX_DOCUMENTS_PER_USER: int = 25
    MAX_STORAGE_BYTES_PER_USER: int = 50 * 1024 * 1024
    MAX_PAGES_PER_DOCUMENT: int = 500
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
