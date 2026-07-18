#!/usr/bin/env bash
# Idempotent redeploy for DMX Advisor on the target server.
# - Fetches the requested branch and hard-resets to it
# - Rebuilds and restarts the docker compose stack
# - Applies migrations (backend entrypoint) and seeds search/RAG indexes
#
# Secrets live in gitignored files that persist across deploys:
#   be1/.env            backend runtime config (keys, service URLs, JWT secrets)
#   deploy/.env.prod    compose interpolation (POSTGRES_PASSWORD, ports, limits)
#
# Usage:  deploy/deploy.sh [branch]   (default: main)
set -euo pipefail

BRANCH="${1:-main}"
REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${REPO_DIR}/deploy/docker-compose.prod.yml"
ENV_FILE="${REPO_DIR}/deploy/.env.prod"

cd "${REPO_DIR}"

echo "==> Deploying branch '${BRANCH}' from ${REPO_DIR}"

if [ ! -f "${REPO_DIR}/be1/.env" ]; then
  echo "ERROR: ${REPO_DIR}/be1/.env is missing. Create it before deploying (see deploy/README.md)." >&2
  exit 1
fi
if [ ! -f "${ENV_FILE}" ]; then
  echo "ERROR: ${ENV_FILE} is missing. Create it before deploying (see deploy/README.md)." >&2
  exit 1
fi

echo "==> Syncing source"
git fetch --prune origin
git checkout -B "${BRANCH}" "origin/${BRANCH}"
git reset --hard "origin/${BRANCH}"

compose() { docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" "$@"; }

echo "==> Building and starting stack"
compose up -d --build

echo "==> Waiting for backend health"
for _ in $(seq 1 40); do
  if compose exec -T backend curl --fail --silent http://localhost:8100/health >/dev/null 2>&1; then
    echo "    backend healthy"
    break
  fi
  sleep 3
done

echo "==> Seeding Elasticsearch product index"
compose exec -T backend python data_ingest/ingest_products.py \
  --elasticsearch-url "http://elasticsearch:9200" --recreate-index || \
  echo "WARN: product ingest failed (continuing)"

echo "==> Building policy RAG index (Qdrant)"
compose exec -T backend python scripts/build_policy_index.py || \
  echo "WARN: policy index build skipped/failed (RAG falls back to lexical)"

echo "==> Pruning dangling images"
docker image prune -f >/dev/null 2>&1 || true

echo "==> Done. Stack status:"
compose ps
