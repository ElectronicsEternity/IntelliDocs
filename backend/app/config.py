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
    BORDERLESS_TABLE_HEADER_GAP: float = 25.0
    BORDERLESS_TABLE_MIN_LINES: int = 3
    TABLE_ROUTINE_MARGIN_RATIO: float = 0.12
    TABLE_ROUTINE_HEADER_MIN_PAGES: int = 3
    TRIAL_MAX_DOCUMENTS: int = 25
    TRIAL_MAX_STORAGE_BYTES: int = 50 * 1024 * 1024
    TRIAL_MAX_PAGES_PER_MONTH: int = 500
    TRIAL_DURATION_DAYS: int = 14
    TRIAL_AI_BUDGET_USD: float = 2.0
    PRO_MAX_DOCUMENTS: int = 250
    PRO_MAX_STORAGE_BYTES: int = 2 * 1024 * 1024 * 1024
    PRO_MAX_PAGES_PER_MONTH: int = 5000
    PRO_AI_BUDGET_USD: float = 20.0
    # Paid Stripe periods snapshot these values so later exchange-rate/config
    # changes cannot alter an allowance which a user has already purchased.
    PRO_AI_ALLOWANCE_MYR: float = 25.0
    BILLING_USD_TO_MYR: float = 4.09
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PRICE_ID: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_EXPECTED_PRICE_MYR: float = 50.0
    STRIPE_RETURN_URL: str = "http://127.0.0.1:5173/"
    # Sandbox only until a separate live-payment readiness review is complete.
    STRIPE_SANDBOX_ONLY: bool = True
    # Enable only after FPX is activated in the same Stripe sandbox.
    STRIPE_FPX_ENABLED: bool = False
    PROCESSING_STALE_AFTER_SECONDS: int = 60 * 60
    # Use the stronger reasoning model selected for production hierarchy retrieval.
    HIERARCHY_PROFILE_MODEL: str = "gpt-5.6-sol"
    # High reasoning improves long-document structural coverage and ordering.
    HIERARCHY_REASONING_EFFORT: str = "high"
    # Leave enough output room for complete legal-document hierarchy JSON.
    HIERARCHY_MAX_OUTPUT_TOKENS: int = 32768
    # Additional targeted correction calls after the initial hierarchy request.
    HIERARCHY_REPAIR_MAX_ATTEMPTS: int = 2
    # Standard USD rates per million tokens; historical records keep a snapshot.
    AI_GPT5_INPUT_RATE: float = 1.25
    AI_GPT5_CACHED_INPUT_RATE: float = 0.125
    AI_GPT5_OUTPUT_RATE: float = 10.0
    AI_GPT5_MINI_INPUT_RATE: float = 0.25
    AI_GPT5_MINI_CACHED_INPUT_RATE: float = 0.025
    AI_GPT5_MINI_OUTPUT_RATE: float = 2.0
    # GPT-5.4 Mini standard rates per million tokens.
    AI_GPT54_MINI_INPUT_RATE: float = 0.75
    AI_GPT54_MINI_CACHED_INPUT_RATE: float = 0.075
    AI_GPT54_MINI_OUTPUT_RATE: float = 4.5
    # GPT-6.1 Sol Standard rates; retain prior model rates for historical usage.
    AI_GPT61_SOL_INPUT_RATE: float = 2.0
    AI_GPT61_SOL_CACHED_INPUT_RATE: float = 0.10
    AI_GPT61_SOL_OUTPUT_RATE: float = 10.0
    AI_GPT56_SOL_INPUT_RATE: float = 4.0
    AI_GPT56_SOL_CACHED_INPUT_RATE: float = 0.4
    AI_GPT56_SOL_OUTPUT_RATE: float = 20.0
    AI_GPT56_TERRA_INPUT_RATE: float = 2.0
    AI_GPT56_TERRA_CACHED_INPUT_RATE: float = 0.2
    AI_GPT56_TERRA_OUTPUT_RATE: float = 12.0
    AI_LONG_CONTEXT_TOKEN_THRESHOLD: int = 272_000
    TABLE_PROFILE_MODEL: str = "gpt-5.6-sol"
    REGULAR_TABLE_MODEL: str = "gpt-5.6-terra"
    SEMANTIC_TABLE_MODEL: str = "gpt-5.6-sol"
    TABLE_REASONING_EFFORT: str = "high"
    TABLE_MAX_OUTPUT_TOKENS: int = 65536
    # Allow one targeted correction when local checks prove a table was omitted.
    TABLE_PROFILE_REPAIR_MAX_ATTEMPTS: int = 1
    AI_EMBEDDING_INPUT_RATE: float = 0.02
    # Group embedding inputs to reduce network requests while staying well
    # below OpenAI's per-request input and token limits.
    EMBEDDING_BATCH_SIZE: int = 100
    # Document selection happens before the existing within-document retrieval.
    DOCUMENT_TITLE_FILENAME_WEIGHT: float = 0.50
    DOCUMENT_DESCRIPTION_WEIGHT: float = 0.35
    DOCUMENT_HIERARCHY_TITLE_WEIGHT: float = 0.15
    # Weak overlap with generic words such as "minimum" is not a document name.
    DOCUMENT_NAME_MATCH_MIN_SCORE: float = 0.60
    DOCUMENT_ROUTING_MIN_SCORE: float = 0.40
    DOCUMENT_ROUTING_MAX_DOCUMENTS: int = 3
    DOCUMENT_FALLBACK_CHUNKS_PER_DOCUMENT: int = 3
    # Final allowance counts complete sections as units, not individual chunks.
    RAG_TOP_K: int = 20
    # Keep each document's candidate allowance independent of the final limit.
    RAG_DOCUMENT_TOP_K: int = 10
    # Capture exact answer requests during local testing; disable for production
    # until private storage and automatic retention are configured.
    RAG_DEBUG_CAPTURE_ENABLED: bool = True
    RAG_DEBUG_CAPTURE_DIRECTORY: Path = Path(__file__).resolve().parents[2] / "logs" / "rag_debug"
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
