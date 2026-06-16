#!/usr/bin/env bash
# Print Celery broker and result-backend DB sizes (Redis DB 0 and 1 by default).
set -euo pipefail

REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_PASSWORD="${REDIS_PASSWORD:-}"

REDIS_CLI=(redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}")
if [[ -n "${REDIS_PASSWORD}" ]]; then
  REDIS_CLI+=(-a "${REDIS_PASSWORD}" --no-auth-warning)
fi

for db in 0 1; do
  count=$("${REDIS_CLI[@]}" -n "${db}" DBSIZE)
  echo "Redis DB ${db}: ${count} keys"
done
