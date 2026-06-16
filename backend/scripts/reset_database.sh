#!/usr/bin/env bash
# Drop and recreate EcoTwin PostgreSQL schema.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-ecotwin}"
POSTGRES_USER="${POSTGRES_USER:-ecotwin}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-changeme}"

export PGPASSWORD="${POSTGRES_PASSWORD}"

PSQL=(psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1)

echo "→ Dropping EcoTwin tables …"
"${PSQL[@]}" -f "${SCRIPT_DIR}/postgres/04_drop_tables.sql"

echo "→ Re-applying schema …"
bash "${SCRIPT_DIR}/setup_database.sh"

echo "✓ Database reset complete"
