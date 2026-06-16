-- Tear down EcoTwin schema (reverse dependency order).
-- Extensions are dropped separately in 05_drop_extensions.sql.

BEGIN;

DROP TABLE IF EXISTS reports CASCADE;
DROP TABLE IF EXISTS temporal_profiles CASCADE;
DROP TABLE IF EXISTS region_embeddings CASCADE;
DROP TABLE IF EXISTS region_features CASCADE;
DROP TABLE IF EXISTS regions CASCADE;

DROP TYPE IF EXISTS report_status_enum;

COMMIT;
