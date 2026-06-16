#!/usr/bin/env bash
# Bootstrap role, database, and schema from scratch (local dev without Docker).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-ecotwin}"
POSTGRES_USER="${POSTGRES_USER:-ecotwin}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-changeme}"
POSTGRES_SUPERUSER="${POSTGRES_SUPERUSER:-postgres}"

export PGPASSWORD="${POSTGRES_SUPERUSER_PASSWORD:-${POSTGRES_PASSWORD}}"

echo "→ Creating role and database (superuser: ${POSTGRES_SUPERUSER}) …"
psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_SUPERUSER}" -d postgres \
  -v ON_ERROR_STOP=1 \
  -v db_name="${POSTGRES_DB}" \
  -v db_user="${POSTGRES_USER}" \
  -v db_password="'${POSTGRES_PASSWORD}'" \
  -f "${SCRIPT_DIR}/postgres/00_create_role_and_database.sql"

export PGPASSWORD="${POSTGRES_PASSWORD}"
bash "${SCRIPT_DIR}/setup_database.sh"

echo "✓ Full database bootstrap complete"
