#!/usr/bin/env bash
set -euo pipefail

# Run pytest on the server against the current Mac working tree.
#
# Usage:
#   ./scripts/remote_pytest.sh [pytest args]
#
# Example:
#   ./scripts/remote_pytest.sh tests/matching/ -v
#   ./scripts/remote_pytest.sh tests/ -q
#   ./scripts/remote_pytest.sh tests/validation/ -v -k "tax"

SERVER="${APMATCH_SERVER:-rith@100.88.94.91}"
REMOTE_DIR="${APMATCH_REMOTE_DEV:-/opt/apmatch-dev}"

# 1. Sync
"$(dirname "$0")/remote_sync.sh"

# 2. Run pytest inside a one-off container with source mounted.
#    -T: no TTY (safe for non-interactive invocations)
#    --rm: remove container when done
#    --entrypoint: override the image's uvicorn entrypoint
ssh "${SERVER}" "cd ${REMOTE_DIR} && \
  if [ ! -f .env.server ]; then echo 'ERROR: ${REMOTE_DIR}/.env.server missing on server' >&2; exit 2; fi && \
  docker compose \
    -f docker-compose.yml \
    -f docker-compose.server.yml \
    -f docker-compose.dev.yml \
    --env-file .env.server \
    run --rm -T \
    --entrypoint /opt/venv/bin/python \
    api -m pytest $*"
