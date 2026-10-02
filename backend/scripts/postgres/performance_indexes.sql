-- EcoTwin API performance indexes (PostgreSQL / Supabase)
--
-- This version works in transaction-wrapping SQL editors (including the
-- Supabase SQL editor). Index creation can briefly block writes to each table.
--
-- These statements are idempotent. Existing primary-key and unique indexes
-- already cover exact ID lookups and (lake_id, year) lookups in several tables.

-- Used by the lakes search endpoint for display_name ILIKE '%term%'.
-- Required by gin_trgm_ops; Supabase normally permits this extension.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Case-insensitive country and substring name filters used by /lakes endpoints.
-- GIN trigram indexes support ILIKE, including leading-wildcard searches.
CREATE INDEX IF NOT EXISTS ix_lakes_country_trgm
    ON lakes USING gin (country gin_trgm_ops);

CREATE INDEX IF NOT EXISTS ix_lakes_display_name_trgm
    ON lakes USING gin (display_name gin_trgm_ops);

-- Similarity scans stream embedding histories in lake/year order. This partial
-- B-tree keeps that ordered scan smaller when some region rows lack embeddings.
CREATE INDEX IF NOT EXISTS ix_regions_embedded_lake_year
    ON regions (lake_id, year)
    WHERE embedding IS NOT NULL;

-- Optional for direct top-K vector-neighbour queries. The exact similarity
-- endpoint streams and scores all lake histories, so it does not use this.
-- Enable only if another active endpoint orders rows by vector distance.
-- CREATE INDEX IF NOT EXISTS ix_regions_embedding_cosine_hnsw
--     ON regions USING hnsw (embedding vector_cosine_ops)
--     WITH (m = 16, ef_construction = 64)
--     WHERE embedding IS NOT NULL;

-- Supports similarity requests that specify method=euclidean.
-- CREATE INDEX IF NOT EXISTS ix_regions_embedding_l2_hnsw
--     ON regions USING hnsw (embedding vector_l2_ops)
--     WITH (m = 16, ef_construction = 64)
--     WHERE embedding IS NOT NULL;

-- Supports similarity requests that specify method=knn (inner product).
-- CREATE INDEX IF NOT EXISTS ix_regions_embedding_ip_hnsw
--     ON regions USING hnsw (embedding vector_ip_ops)
--     WITH (m = 16, ef_construction = 64)
--     WHERE embedding IS NOT NULL;

-- Supports selecting completed subregion embedding years for /embeddings/merge/options.
CREATE INDEX IF NOT EXISTS ix_sub_regions_completed_embedding_year
    ON sub_regions (year)
    WHERE status = 'completed' AND embedding IS NOT NULL;

-- lake_tiles has a unique (lake_id, year, tile_index) index already. This
-- ordering matches GET /imagery/lakes/{lake_id}: newest year first, tile index
-- ascending within a year.
CREATE INDEX IF NOT EXISTS ix_lake_tiles_lake_year_desc_tile
    ON lake_tiles (lake_id, year DESC, tile_index ASC);

-- KNN spatial index for nearest-region lookup. The current Python query uses
-- POW(center_lat - :lat, 2) + POW(center_lon - :lon, 2), so it will NOT use this
-- index until the query is rewritten to order by the same geography expression
-- with the <-> operator, e.g.:
--
-- SELECT region_id, center_lat, center_lon
-- FROM regions
-- ORDER BY
--   (ST_SetSRID(ST_MakePoint(center_lon, center_lat), 4326)::geography)
--   <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
-- LIMIT 1;
CREATE INDEX IF NOT EXISTS ix_regions_center_geography_gist
    ON regions USING gist (
        (ST_SetSRID(ST_MakePoint(center_lon, center_lat), 4326)::geography)
    );

-- Refresh planner statistics after index creation.
ANALYZE lakes;
ANALYZE regions;
ANALYZE sub_regions;
ANALYZE lake_tiles;
