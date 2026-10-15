#!/usr/bin/env bash
set -euo pipefail

# Deploy APMatch to the remote server.
#
# Usage:
#   ./scripts/deploy_remote.sh <ssh-target>
#
# Example:
#   ./scripts/deploy_remote.sh rith@100.76.126.16
#
# Assumptions:
#   - SSH key auth is configured (no password prompts).
#   - The remote has a working Docker installation.
#   - The remote has been provisioned once with `scripts/provision_remote.sh`
#     (creates /opt/apmatch, installs nothing else).
#
# This script is idempotent: running it twice produces the same state.

SSH_TARGET="${1:?usage: $0 <ssh-target>}"
REMOTE_DIR="/opt/apmatch"

echo "Deploying to ${SSH_TARGET}:${REMOTE_DIR}"

# 1. Sync source. models/ IS included: the Dockerfile COPYs it into the
# image, and it's gitignored, so rsync is the only transfer mechanism.
# First run syncs ~1.2 GB over Tailscale; later runs are incremental.
rsync -az --delete \
  --exclude='.git/' \
  --exclude='.venv/' \
  --exclude='.env.server' \
  --exclude='output/' \
  --exclude='documents/' \
  --exclude='test_docs/' \
  --exclude='*.db' \
  --exclude='__pycache__/' \
  --exclude='.pytest_cache/' \
  --exclude='.ruff_cache/' \
  ./ "${SSH_TARGET}:${REMOTE_DIR}/"

# 2. Build and start on the remote
ssh "${SSH_TARGET}" bash -s <<'REMOTE'
  set -euo pipefail
  cd /opt/apmatch
  if [ ! -f .env.server ]; then
    echo "ERROR: .env.server missing on remote. Copy .env.server.example and fill in values." >&2
    exit 2
  fi
  docker compose -f docker-compose.yml -f docker-compose.server.yml \
    --env-file .env.server \
    up -d --build
  echo "Waiting for healthz..."
  # Check inside the container so this works regardless of the host port
  # mapping (the server override publishes the API on 8001, not 8000).
  for i in $(seq 1 90); do
    if docker compose -f docker-compose.yml -f docker-compose.server.yml \
        --env-file .env.server \
        exec -T api curl -fsS http://localhost:8000/healthz >/dev/null 2>&1; then
      echo "DEPLOY OK"
      exit 0
    fi
    sleep 2
  done
  echo "ERROR: healthz did not respond within 180 seconds" >&2
  docker compose -f docker-compose.yml -f docker-compose.server.yml \
    --env-file .env.server logs api --tail=50 >&2
  exit 3
REMOTE

echo "Deploy complete."
