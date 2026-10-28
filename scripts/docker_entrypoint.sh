#!/usr/bin/env bash
set -euo pipefail

# Container entrypoint for the APMatch API image.
# Runs Alembic migrations (idempotent) before starting uvicorn.
# Safe on fresh DBs (creates schema) and existing DBs (no-op
# if migrations already applied).

echo "[entrypoint] Applying database migrations..."
alembic upgrade head

echo "[entrypoint] Starting application: $*"
exec "$@"
