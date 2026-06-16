-- EcoTwin indexes – btree lookups + pgvector IVFFlat cosine index.
-- Safe to re-run (IF NOT EXISTS).

-- ── regions ──────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_regions_coords
    ON regions (center_lat, center_lon);

CREATE INDEX IF NOT EXISTS idx_regions_geom
    ON regions USING GIST (geom);

-- ── region_features ──────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_rf_region_id
    ON region_features (region_id);

CREATE INDEX IF NOT EXISTS idx_rf_year
    ON region_features (year);

-- ── region_embeddings ────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_re_region_id
    ON region_embeddings (region_id);

CREATE INDEX IF NOT EXISTS idx_re_year
    ON region_embeddings (year);

-- IVFFlat cosine index for sub-500 ms similarity search (requires pgvector).
-- Rebuild with REINDEX after bulk embedding loads for best recall.
CREATE INDEX IF NOT EXISTS idx_region_embedding_cosine
    ON region_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ── temporal_profiles ────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_tp_region_id
    ON temporal_profiles (region_id);

CREATE INDEX IF NOT EXISTS idx_tp_year
    ON temporal_profiles (year);

-- ── reports ──────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_reports_region_id
    ON reports (region_id);

CREATE INDEX IF NOT EXISTS idx_reports_status
    ON reports (status);

CREATE INDEX IF NOT EXISTS idx_reports_generated_at
    ON reports (generated_at DESC);
