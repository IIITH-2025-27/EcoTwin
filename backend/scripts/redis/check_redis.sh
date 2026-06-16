#!/usr/bin/env bash
# Verify Redis connectivity and optionally flush the EcoTwin cache namespace.
set -euo pipefail

REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_PASSWORD="${REDIS_PASSWORD:-}"
FLUSH="${1:-}"

REDIS_CLI=(redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}")
if [[ -n "${REDIS_PASSWORD}" ]]; then
  REDIS_CLI+=(-a "${REDIS_PASSWORD}" --no-auth-warning)
fi

echo "→ Pinging Redis at ${REDIS_HOST}:${REDIS_PORT} …"
if ! "${REDIS_CLI[@]}" ping | grep -q PONG; then
  echo "✗ Redis is not reachable" >&2
  exit 1
fi

echo "✓ Redis is up"

if [[ "${FLUSH}" == "--flush" ]]; then
  echo "→ Flushing all Redis databases (FLUSHALL) …"
  "${REDIS_CLI[@]}" FLUSHALL
  echo "✓ Redis cache cleared"
fi
