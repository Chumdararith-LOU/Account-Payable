#!/usr/bin/env bash
set -euo pipefail

# Verify the offline guarantee holds inside the deployed container.
#
# Usage:
#   ./scripts/verify_offline_remote.sh <ssh-target>
#
# Runs `scripts/verify_offline.py` inside the running api container.

SSH_TARGET="${1:?usage: $0 <ssh-target>}"
# Keepalives: the OCR pass takes minutes and the link is flaky.
ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=4 "${SSH_TARGET}" bash -s <<'REMOTE'
  set -euo pipefail
  cd /opt/apmatch
  docker compose -f docker-compose.yml -f docker-compose.server.yml \
    --env-file .env.server \
    exec -T api python scripts/verify_offline.py
REMOTE
