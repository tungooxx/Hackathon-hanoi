#!/usr/bin/env bash
# Poll-based CD: redeploy only when origin/<branch> advanced past the local HEAD.
# Invoked by the systemd timer (dmx-deploy.timer) every couple of minutes.
set -euo pipefail

BRANCH="${1:-main}"
REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK="/tmp/dmx-deploy.lock"

cd "${REPO_DIR}"

# Prevent overlapping runs
exec 9>"${LOCK}"
if ! flock -n 9; then
  echo "$(date -Is) another deploy is running, skipping"
  exit 0
fi

git fetch --quiet origin "${BRANCH}"
LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse "origin/${BRANCH}")"

if [ "${LOCAL}" = "${REMOTE}" ]; then
  echo "$(date -Is) up-to-date at ${LOCAL:0:8}"
  exit 0
fi

echo "$(date -Is) new commit ${REMOTE:0:8} (was ${LOCAL:0:8}) — deploying"
exec "${REPO_DIR}/deploy/deploy.sh" "${BRANCH}"
