#!/usr/bin/env bash
# Apply EcoTwin PostgreSQL schema (extensions, tables, indexes).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POSTGRES_DIR="${SCRIPT_DIR}/postgres"

POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-ecotwin}"
POSTGRES_USER="${POSTGRES_USER:-ecotwin}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-changeme}"

export PGPASSWORD="${POSTGRES_PASSWORD}"

PSQL=(psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1)

echo "→ Applying extensions …"
"${PSQL[@]}" -f "${POSTGRES_DIR}/01_extensions.sql"

echo "→ Creating tables …"
"${PSQL[@]}" -f "${POSTGRES_DIR}/02_create_tables.sql"

echo "→ Creating indexes …"
"${PSQL[@]}" -f "${POSTGRES_DIR}/03_indexes.sql"

echo "→ Applying grants …"
"${PSQL[@]}" -f "${POSTGRES_DIR}/06_grants.sql"

echo "✓ Database schema ready on ${POSTGRES_DB}@${POSTGRES_HOST}:${POSTGRES_PORT}"
