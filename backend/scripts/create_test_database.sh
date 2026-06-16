#!/usr/bin/env bash
# Create ecotwin_test database and apply the same schema (for pytest integration tests).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-ecotwin}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-changeme}"
TEST_DB="${POSTGRES_TEST_DB:-ecotwin_test}"

export PGPASSWORD="${POSTGRES_PASSWORD}"

echo "→ Ensuring test database '${TEST_DB}' exists …"
psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d postgres \
  -v ON_ERROR_STOP=1 \
  -v test_db_name="${TEST_DB}" \
  -v db_user="${POSTGRES_USER}" \
  -f "${SCRIPT_DIR}/postgres/00_create_test_database.sql"

POSTGRES_DB="${TEST_DB}" bash "${SCRIPT_DIR}/setup_database.sh"

echo "✓ Test database '${TEST_DB}' is ready"
