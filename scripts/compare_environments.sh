#!/usr/bin/env bash
set -euo pipefail

# Compare pipeline output between Mac (local) and server (remote).
#
# Usage (Mac, with the anpr conda env active):
#   ./scripts/compare_environments.sh
#
# Output:
#   /tmp/dump_mac.json       (local dump)
#   /tmp/dump_server.json    (fetched from the server)
#   /tmp/determinism_diff.txt  (structured diff)
#
# Exit codes:
#   0 — outputs identical (or within tolerance)
#   1 — differences found (see /tmp/determinism_diff.txt)
#   2 — script failure (SSH, missing files, etc.)
#
# The server dump runs in a detached one-off container (kept alive until the
# JSON is copied out), so it survives local SSH disconnects. The production
# API is NOT touched.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

SERVER="${APMATCH_SERVER:-rith@100.127.105.9}"
LOCAL_DUMP="/tmp/dump_mac.json"
REMOTE_DUMP="/tmp/dump_server.json"
DIFF_OUT="/tmp/determinism_diff.txt"

DUMP_ARGS=(
  --invoice documents/invoice/INV_2026_1123.png
  --po documents/po/PO_2026_0451.png
  --grni documents/grni/GRN_2026_0322.png
  --pard documents/pard/PARD_2026_0210.png
  --extra documents/invoice/invoice.png
  --extra "documents/invoice/Pasted image.png"
)

# 1. Local dump
echo ">>> Running pipeline locally..."
python scripts/dump_pipeline_output.py "${DUMP_ARGS[@]}" --out "$LOCAL_DUMP"
echo "    wrote $LOCAL_DUMP"

# 2. Sync source, then run the dump on the server in a detached container
echo ">>> Syncing source to server..."
./scripts/remote_sync.sh

echo ">>> Running pipeline on server (detached container, ~40-70 min)..."
ssh "$SERVER" bash -s <<'REMOTE'
set -euo pipefail
cd /opt/apmatch-dev
docker rm -f apmatch-dump-tmp 2>/dev/null || true
docker compose \
  -f docker-compose.yml \
  -f docker-compose.server.yml \
  -f docker-compose.dev.yml \
  --env-file .env.server \
  run -d --name apmatch-dump-tmp \
  --entrypoint /opt/venv/bin/python \
  api scripts/dump_pipeline_output.py \
    --invoice documents/invoice/INV_2026_1123.png \
    --po documents/po/PO_2026_0451.png \
    --grni documents/grni/GRN_2026_0322.png \
    --pard documents/pard/PARD_2026_0210.png \
    --extra documents/invoice/invoice.png \
    --extra "documents/invoice/Pasted image.png" \
    --out /app/_dump_server.json
# Wait up to 90 minutes for the container to exit.
for i in $(seq 1 2700); do
  if ! docker ps --format '{{.Names}}' | grep -q apmatch-dump-tmp; then
    break
  fi
  sleep 2
done
if docker ps --format '{{.Names}}' | grep -q apmatch-dump-tmp; then
  echo "ERROR: dump container still running after 90 min" >&2
  docker logs apmatch-dump-tmp 2>&1 | tail -20 >&2
  docker rm -f apmatch-dump-tmp
  exit 2
fi
docker cp apmatch-dump-tmp:/app/_dump_server.json /tmp/dump_server.json
docker rm -f apmatch-dump-tmp
echo "server dump copied to /tmp/dump_server.json"
REMOTE

# 3. Fetch the dump
scp "$SERVER:/tmp/dump_server.json" "$REMOTE_DUMP"

# 4. Structured diff
echo ">>> Comparing..."
python scripts/compare_json_dumps.py "$LOCAL_DUMP" "$REMOTE_DUMP" > "$DIFF_OUT" || true
cat "$DIFF_OUT"

if grep -q "^DIFFERENCES: [1-9]" "$DIFF_OUT"; then
  echo ">>> Differences found (see $DIFF_OUT)"
  exit 1
fi
echo ">>> No differences."
exit 0
