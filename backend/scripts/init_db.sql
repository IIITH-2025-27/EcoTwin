-- Initialisation script executed once when the PostgreSQL container first starts.
-- Enables required extensions; full schema is applied via Alembic or scripts/setup_database.sh.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;

-- Optional: uncomment to auto-create tables on first container boot (instead of Alembic).
-- \i /docker-entrypoint-initdb.d/postgres/02_create_tables.sql
-- \i /docker-entrypoint-initdb.d/postgres/03_indexes.sql
