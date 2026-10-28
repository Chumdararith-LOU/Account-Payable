#!/usr/bin/env bash
set -euo pipefail

# Sync the Mac working tree to the server's dev mirror.
# Called by remote_pytest.sh and remote.sh; can also be run
# directly.
#
# Environment:
#   APMATCH_SERVER   default: rith@100.88.94.91
#   APMATCH_REMOTE_DEV   default: /opt/apmatch-dev

SERVER="${APMATCH_SERVER:-rith@100.88.94.91}"
REMOTE_DIR="${APMATCH_REMOTE_DEV:-/opt/apmatch-dev}"

# Create the remote dir if missing (idempotent).
ssh "${SERVER}" "mkdir -p ${REMOTE_DIR}"

# Sync. Excludes mirror .gitignore plus a few extras that must
# never cross the wire.
rsync -az --delete \
  --exclude='.git/' \
  --exclude='.venv/' \
  --exclude='venv/' \
  --exclude='models/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='*.pyo' \
  --exclude='.pytest_cache/' \
  --exclude='.ruff_cache/' \
  --exclude='*.db' \
  --exclude='*.db-journal' \
  --exclude='.env' \
  --exclude='.env.server' \
  --exclude='*.log' \
  --exclude='output/imgs/' \
  --exclude='erp_queue/' \
  --exclude='pending_queue/' \
  --exclude='review_queue/' \
  --exclude='ap_automation.db*' \
  --exclude='*.pdf' \
  --exclude='VGM_OCL*' \
  --exclude='vgm_ocl_split/' \
  --exclude='.DS_Store' \
  ./ "${SERVER}:${REMOTE_DIR}/"

echo "Synced to ${SERVER}:${REMOTE_DIR}"
