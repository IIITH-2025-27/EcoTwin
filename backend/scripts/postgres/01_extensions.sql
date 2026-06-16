-- Required PostgreSQL extensions for EcoTwin (PostGIS + pgvector).
-- Safe to re-run.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
