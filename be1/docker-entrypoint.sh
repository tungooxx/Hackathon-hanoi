#!/usr/bin/env bash
# Waits for Postgres, applies Alembic migrations, then runs the given command
# (uvicorn by default). Idempotent — safe to run on every container start.
set -euo pipefail

echo "[entrypoint] waiting for database migrations..."
for attempt in $(seq 1 60); do
  if alembic upgrade head; then
    echo "[entrypoint] migrations applied."
    break
  fi
  echo "[entrypoint] alembic not ready yet (attempt ${attempt}/60), retrying in 3s..."
  sleep 3
  if [ "${attempt}" -eq 60 ]; then
    echo "[entrypoint] migrations failed after retries" >&2
    exit 1
  fi
done

echo "[entrypoint] starting: $*"
exec "$@"
