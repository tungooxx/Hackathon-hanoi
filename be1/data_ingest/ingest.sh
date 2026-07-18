#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../docker/docker-compose.yml"
ELASTICSEARCH_URL="${ELASTICSEARCH_URL:-http://127.0.0.1:9200}"

docker compose -f "${COMPOSE_FILE}" up -d elasticsearch

for _attempt in $(seq 1 120); do
  if curl --fail --silent "${ELASTICSEARCH_URL}/" >/dev/null; then
    break
  fi
  sleep 1
done

if ! curl --fail --silent "${ELASTICSEARCH_URL}/" >/dev/null; then
  docker compose -f "${COMPOSE_FILE}" logs --tail=100 elasticsearch
  echo "Elasticsearch did not become ready at ${ELASTICSEARCH_URL}" >&2
  exit 1
fi

exec python3 "${SCRIPT_DIR}/ingest_products.py" \
  --elasticsearch-url "${ELASTICSEARCH_URL}" \
  --recreate-index \
  "$@"
