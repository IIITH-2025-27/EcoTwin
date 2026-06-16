-- EcoTwin core schema – tables only (indexes in 03_indexes.sql).
-- Mirrors alembic revision 001_initial_schema.py.

BEGIN;

-- ── regions ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS regions (
    region_id   UUID PRIMARY KEY,
    center_lat  DOUBLE PRECISION NOT NULL,
    center_lon  DOUBLE PRECISION NOT NULL,
    area_km     DOUBLE PRECISION DEFAULT 25.0,
    geom        GEOMETRY(POLYGON, 4326),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── region_features ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS region_features (
    id                  UUID PRIMARY KEY,
    region_id           UUID NOT NULL REFERENCES regions (region_id) ON DELETE CASCADE,
    year                INTEGER NOT NULL,
    ndvi_mean           DOUBLE PRECISION,
    ndvi_std            DOUBLE PRECISION,
    ndvi_median         DOUBLE PRECISION,
    ndvi_min            DOUBLE PRECISION,
    ndvi_max            DOUBLE PRECISION,
    ndwi_mean           DOUBLE PRECISION,
    ndwi_std            DOUBLE PRECISION,
    ndwi_median         DOUBLE PRECISION,
    ndwi_min            DOUBLE PRECISION,
    ndwi_max            DOUBLE PRECISION,
    nbr_mean            DOUBLE PRECISION,
    nbr_std             DOUBLE PRECISION,
    nbr_median          DOUBLE PRECISION,
    nbr_min             DOUBLE PRECISION,
    nbr_max             DOUBLE PRECISION,
    dominant_ecosystem  VARCHAR(100),
    CONSTRAINT uq_region_feature_year UNIQUE (region_id, year)
);

-- ── region_embeddings ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS region_embeddings (
    id          UUID PRIMARY KEY,
    region_id   UUID NOT NULL REFERENCES regions (region_id) ON DELETE CASCADE,
    year        INTEGER NOT NULL,
    embedding   VECTOR(768) NOT NULL,
    CONSTRAINT uq_region_embedding_year UNIQUE (region_id, year)
);

-- ── temporal_profiles ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS temporal_profiles (
    id          UUID PRIMARY KEY,
    region_id   UUID NOT NULL REFERENCES regions (region_id) ON DELETE CASCADE,
    year        INTEGER NOT NULL,
    ndvi        DOUBLE PRECISION,
    ndwi        DOUBLE PRECISION,
    nbr         DOUBLE PRECISION,
    CONSTRAINT uq_temporal_profile_year UNIQUE (region_id, year)
);

-- ── reports ──────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'report_status_enum') THEN
        CREATE TYPE report_status_enum AS ENUM (
            'pending',
            'processing',
            'completed',
            'failed'
        );
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS reports (
    report_id       UUID PRIMARY KEY,
    region_id       UUID NOT NULL REFERENCES regions (region_id) ON DELETE CASCADE,
    generated_at    TIMESTAMPTZ DEFAULT NOW(),
    pdf_url         TEXT,
    status          report_status_enum NOT NULL DEFAULT 'pending',
    celery_task_id  VARCHAR(255),
    error_message   TEXT
);

COMMIT;
