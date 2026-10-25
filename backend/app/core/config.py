from functools import lru_cache
from typing import List, Optional
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url


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

    # ── Database URL Override ─────────────────────────────────────
    # Leave empty for normal local PostgreSQL development.
    # Set this when connecting to an external/hosted PostgreSQL
    # database such as Supabase.
    # When set, it takes precedence over all POSTGRES_* variables.
    #
    # Example:
    #   DATABASE_URL_OVERRIDE=postgresql+asyncpg://user:pass@host:5432/db
    DATABASE_URL_OVERRIDE: Optional[str] = None

    # ── Server ────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4

    # ── PostgreSQL (local fallback) ───────────────────────────────
    # Used only when DATABASE_URL_OVERRIDE is empty or not set.
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
    SIMILARITY_BATCH_SIZE: int = 50

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

    # Maximum years a single sync job can span
    SYNC_MAX_YEAR_RANGE: int = 10

    # ── ML Pipeline ───────────────────────────────────────────────────────────
    # Path to a local Prithvi-100M directory/checkpoint within the workspace
    PRITHVI_MODEL_PATH: str = "app/ML_models/Prithvi-EO-1.0-100M"
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

    # ── Image Acquisition Pipeline ────────────────────────────────
    SENTINEL_DATA_DIR: str = "data/sentinel"
    # 3.5 km gives every lake grid cell Prithvi's full 224 px × 30 m
    # (6.72 km) context window without padding.
    LAKE_IMAGERY_BUFFER_METRES: int = 3_500
    # Transient GEE errors (HTTP 503 / timeouts) are retried with backoff
    IMAGERY_MAX_RETRIES: int = 3
    IMAGERY_RETRY_DELAY_SEC: float = 5.0
    IMAGERY_RETRY_BACKOFF: float = 2.0
    IMAGERY_DOWNLOAD_TIMEOUT_SEC: int = 600
    IMAGERY_BATCH_SIZE: int = 10
    # Tiles are cut in EPSG:6933 but downloaded in EPSG:4326 at 30 m, so
    # pixel counts grow with latitude. 25 km tiles with 12 uint16 bands are
    # ≤ 20.4 MB across India (8°–35° N), under GEE's documented 32 MB
    # getDownloadURL limit; 30 km would reach 29.4 MB at 35° N.
    IMAGERY_TILE_SIZE_METRES: int = 25_000
    IMAGERY_DOWNLOAD_WORKERS: int = 2
    IMAGERY_LAKE_WORKERS: int = 4

    IMAGE_ACQUISITION_MODE: str = "tile"
    # tile | drive
    GEE_DRIVE_FOLDER: str = "EcoTwin"
    GEE_DRIVE_POLL_INTERVAL_SEC: int = 20
    GEE_DRIVE_TIMEOUT_MIN: int = 180
    USE_GEE_SERVICE_ACCOUNT: bool = True

    # ── Embedding Pipeline ────────────────────────────────────────
    # Shoreline ring pooled into the shore embedding, outside the lake
    # polygon. 500 m ≈ one 30 m Prithvi token and covers the lake's own
    # water-level fluctuation zone (JRC Global Surface Water analysis).
    EMBEDDING_SHORE_RING_METRES: int = 500
    # Weight of the lake part in the combined embedding:
    #   embedding = normalize(w · lake + (1 − w) · shore)
    # Re-blendable later from the stored parts via POST /embeddings/merge.
    EMBEDDING_LAKE_WEIGHT: float = 0.7
    # A lake-year needs at least this many valid (cloud-free) 30 m lake
    # pixels for a usable embedding (100 px ≈ 9 ha).
    EMBEDDING_MIN_LAKE_PIXELS: int = 100

    # ── Internal helpers ──────────────────────────────────────────

    @property
    def _has_override(self) -> bool:
        """True when DATABASE_URL_OVERRIDE contains a non-empty, non-whitespace value."""
        return bool(self.DATABASE_URL_OVERRIDE and self.DATABASE_URL_OVERRIDE.strip())

    @property
    def DATABASE_URL(self) -> str:
        """Async database URL for SQLAlchemy / FastAPI (asyncpg driver).

        Uses DATABASE_URL_OVERRIDE when provided; otherwise constructs
        from POSTGRES_* variables.
        """
        if self._has_override:
            override = self.DATABASE_URL_OVERRIDE.strip()  # type: ignore[union-attr]
            # Ensure the asyncpg driver is used. Use SQLAlchemy's
            # make_url so we never manually parse/reconstruct the URL
            # (passwords may contain special characters like @, :, /).
            parsed = make_url(override)
            if parsed.drivername not in ("postgresql+asyncpg",):
                parsed = parsed.set(drivername="postgresql+asyncpg")
            return parsed.render_as_string(hide_password=False)

        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        ).render_as_string(hide_password=False)

    @property
    def SYNC_DATABASE_URL(self) -> str:
        """Synchronous database URL for Alembic migrations (psycopg2 driver).

        Uses DATABASE_URL_OVERRIDE when provided; otherwise constructs
        from POSTGRES_* variables.  The driver is always set to
        ``postgresql+psycopg2`` via SQLAlchemy's ``make_url`` to avoid
        corrupting passwords that contain special characters.
        """
        if self._has_override:
            override = self.DATABASE_URL_OVERRIDE.strip()  # type: ignore[union-attr]
            # Safely swap the driver to psycopg2 without touching the
            # rest of the URL (host, password, path, query params).
            parsed = make_url(override)
            parsed = parsed.set(drivername="postgresql+psycopg2")
            return parsed.render_as_string(hide_password=False)

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
