-- One-shot EcoTwin schema bootstrap (extensions + tables + indexes).
-- Usage:  psql -U ecotwin -d ecotwin -f 99_full_schema.sql

\ir 01_extensions.sql
\ir 02_create_tables.sql
\ir 03_indexes.sql
\ir 06_grants.sql
