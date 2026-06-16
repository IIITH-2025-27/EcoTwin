-- Remove extensions (only when fully resetting the database).
-- Requires all dependent objects to be dropped first.

DROP EXTENSION IF EXISTS vector;
DROP EXTENSION IF EXISTS postgis;
