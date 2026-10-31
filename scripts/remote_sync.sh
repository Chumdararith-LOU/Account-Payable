#!/usr/bin/env bash
set -euo pipefail

# Sync the committed Mac state to the server via git (push + pull).
# Called by remote_pytest.sh and remote.sh; can also be run directly.
#
# Git is the transport now (was rsync): the Mac pushes, the server pulls.
# Uncommitted local changes do NOT flow — commit first. The server copy
# keeps its untracked extras (batch data, .env.server, reports/, output/);
# model weights are baked into the image, not synced.
#
# Environment:
#   APMATCH_SERVER   default: rith@100.88.94.91
#   APMATCH_REMOTE_DEV   default: /home/rith/apmatch-dev

SERVER="${APMATCH_SERVER:-rith@100.88.94.91}"
REMOTE_DIR="${APMATCH_REMOTE_DEV:-/home/rith/apmatch-dev}"

git push origin HEAD
ssh "${SERVER}" "git -C ${REMOTE_DIR} pull --ff-only"

echo "Synced (git push+pull) to ${SERVER}:${REMOTE_DIR}"
