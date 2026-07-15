from functools import lru_cache
from typing import List
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
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
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "1234567890"


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

    # ── Object Storage (PDF reports) ──────────────────────────────
    REPORTS_STORAGE_PATH: str = "/app/reports"
    S3_BUCKET: str = ""
    S3_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""

    # ── Data-sync boundary sources ───────────────────────────────────────────
    HYDROLAKES_SOURCE_PATH: str = "" 

    HYDROLAKES_SHAPEFILE_PATH: str = "" 
    INDIA_STATES_SOURCE_PATH: str = ""

    # ── Lake processing grid ────────────────────────────────────────────────
    # Grid dimensions are metres in an equal-area CRS (EPSG:6933).
    LAKE_GRID_CELL_SIZE_METRES: int = 1_000
    # Ignore a grid cell when less than this percentage is covered by lake.
    LAKE_GRID_MIN_COVERAGE_PERCENT: float = 15.0
    # Maximum years a single sync job can span
    SYNC_MAX_YEAR_RANGE: int = 10

    # ── ML Pipeline ───────────────────────────────────────────────────────────
    # Path to a local Prithvi-100M directory/checkpoint within the workspace
    PRITHVI_MODEL_PATH: str = "app/ML_models/Prithvi-EO-1.0-100M/Prithvi-EO-1.0-100M"
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
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        ).render_as_string(hide_password=False)

    @property
    def SYNC_DATABASE_URL(self) -> str:  # noqa: N802
        return URL.create(
            drivername="postgresql+psycopg2",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        ).render_as_string(hide_password=False)


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
