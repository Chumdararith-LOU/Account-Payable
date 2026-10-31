#!/usr/bin/env bash
set -euo pipefail

# Run an arbitrary command on the server against the current
# Mac working tree.
#
# Usage:
#   ./scripts/remote.sh <shell command>
#
# Example:
#   ./scripts/remote.sh 'ruff check apmatch/ tests/'
#   ./scripts/remote.sh 'python scripts/diagnose_match_failure.py'
#   ./scripts/remote.sh 'alembic upgrade head'

SERVER="${APMATCH_SERVER:-rith@100.88.94.91}"
REMOTE_DIR="${APMATCH_REMOTE_DEV:-/home/rith/apmatch-dev}"

# Sync first
"$(dirname "$0")/remote_sync.sh"

# ruff lives in requirements-dev.txt, which the image does not install,
# and the container runs non-root (no write to /opt/venv, no --user in a
# venv). --target /tmp is writable and the container is one-off (--rm), so
# this throwaway install is cheap.
CMD="$*"
case "$CMD" in
  ruff*) CMD="pip install -q --target /tmp/ruffpkgs \"ruff==0.16.9\" && export PATH=/tmp/ruffpkgs/bin:\$PATH && $CMD" ;;
esac

# Run inside a one-off container with source mounted
ssh "${SERVER}" "cd ${REMOTE_DIR} && \
  if [ ! -f .env.server ]; then echo 'ERROR: ${REMOTE_DIR}/.env.server missing on server' >&2; exit 2; fi && \
  docker compose \
    -f docker-compose.yml \
    -f docker-compose.server.yml \
    -f docker-compose.dev.yml \
    --env-file .env.server \
    run --rm -T \
    --entrypoint /bin/bash \
    api -c '$CMD'"
