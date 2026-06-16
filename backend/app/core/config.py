from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Application ───────────────────────────────────────────────
    APP_NAME: str = "EcoTwin API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"

    # ── Server ────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4

    # ── PostgreSQL ────────────────────────────────────────────────
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "ecotwin"
    POSTGRES_USER: str = "ecotwin"
    POSTGRES_PASSWORD: str = "changeme"

    # ── Redis ─────────────────────────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_TTL: int = 86_400  # 24 hours

    # ── JWT ───────────────────────────────────────────────────────
    SECRET_KEY: str = "CHANGE_THIS_IN_PRODUCTION"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # ── Similarity Search ─────────────────────────────────────────
    DEFAULT_TOP_K: int = 10
    MAX_TOP_K: int = 50
    SIMILARITY_TARGET_MS: int = 500

    # ── CORS ──────────────────────────────────────────────────────
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # ── Celery ────────────────────────────────────────────────────
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # ── Object Storage (PDF reports) ──────────────────────────────
    REPORTS_STORAGE_PATH: str = "/app/reports"
    S3_BUCKET: str = ""
    S3_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    # ── ML Pipeline ───────────────────────────────────────────────────────────
    # Path to a local Prithvi-100M .pt checkpoint; falls back to HuggingFace hub
    PRITHVI_MODEL_PATH: str = "/app/models/prithvi_100m.pt"
    # When True, Prithvi inference returns a deterministic stub embedding
    # (no GPU / model weights required).  Automatically True when DEBUG=true.
    PRITHVI_USE_STUB: bool = False
    # GEE service-account JSON key; leave empty to use user credentials
    # (run `earthengine authenticate` once for user-credential flow)
    GEE_SERVICE_ACCOUNT_KEY_PATH: str = ""
    GEE_SERVICE_ACCOUNT_EMAIL: str = ""
    # Optional path to a serialised sklearn classifier (.pkl) for ecosystem
    # classification.  Leave empty to use the built-in rule-based classifier.
    CLASSIFIER_MODEL_PATH: str = ""
    # ── Computed properties ───────────────────────────────────────
    @property
    def DATABASE_URL(self) -> str:  # noqa: N802
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def SYNC_DATABASE_URL(self) -> str:  # noqa: N802
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def REDIS_URL(self) -> str:  # noqa: N802
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
