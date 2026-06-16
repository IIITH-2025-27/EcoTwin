-- Initialisation script executed once when the PostgreSQL container first starts.
-- The pgvector extension ships pre-installed in the pgvector/pgvector image.
-- PostGIS is installed via the postgis/postgis image tag OR via apt in a custom image.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
