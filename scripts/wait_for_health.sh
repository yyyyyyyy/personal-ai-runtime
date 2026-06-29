#!/usr/bin/env bash
# Wait until backend health endpoint responds (used by `make dev`).
set -euo pipefail

HOST="${1:-localhost}"
PORT="${2:-8000}"
TIMEOUT="${3:-60}"
URL="http://${HOST}:${PORT}/api/system/health"

echo "Waiting for backend at ${URL} (timeout ${TIMEOUT}s)..."
for i in $(seq 1 "$TIMEOUT"); do
  if curl -sf "$URL" >/dev/null 2>&1; then
    echo "Backend is ready."
    exit 0
  fi
  sleep 1
done

echo "ERROR: Backend did not become ready within ${TIMEOUT}s" >&2
exit 1
