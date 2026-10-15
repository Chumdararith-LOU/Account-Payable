#!/usr/bin/env bash
set -euo pipefail

# Full-stack smoke test. Brings up the compose stack, POSTs the
# four fixture images, verifies the audit trail, tears down.
# Exit 0 on success, non-zero on any failure.
#
# Usage:
#   APMATCH_API_KEY=<32 hex chars> ./scripts/smoke_test.sh
#
# If APMATCH_API_KEY is unset, the script generates one with
# `python -c "import secrets; print(secrets.token_hex(32))"`.
#
# Requires: docker (compose v2), curl, and python (or python3) on PATH
# for JSON parsing.

REPO_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$REPO_ROOT"

# Python for JSON parsing (python or python3 on PATH).
PY="$(command -v python || command -v python3 || true)"
if [ -z "$PY" ]; then
  echo "ERROR: neither python nor python3 on PATH (needed for JSON parsing)" >&2
  exit 2
fi

# Portable bounded wait (no GNU `timeout`, which is absent on macOS).
# wait_for <seconds> <command...> -> runs the command until it exits 0 or the
# deadline passes; returns 1 on timeout, else the command's last status.
wait_for() {
  local deadline=$((SECONDS + $1)); shift
  while ! "$@" >/dev/null 2>&1; do
    if [ "$SECONDS" -ge "$deadline" ]; then
      return 1
    fi
    sleep 1
  done
  return 0
}

# 1. Resolve API key
if [ -z "${APMATCH_API_KEY:-}" ]; then
  export APMATCH_API_KEY="$("$PY" -c 'import secrets; print(secrets.token_hex(32))')"
  echo "Generated APMATCH_API_KEY (length: ${#APMATCH_API_KEY})"
fi

# 2. Fixture paths
INVOICE="${REPO_ROOT}/documents/invoice/INV_2026_1123.png"
PO="${REPO_ROOT}/documents/po/PO_2026_0451.png"
GRNI="${REPO_ROOT}/documents/grni/GRN_2026_0322.png"
PARD="${REPO_ROOT}/documents/pard/PARD_2026_0210.png"

for f in "$INVOICE" "$PO" "$GRNI" "$PARD"; do
  if [ ! -f "$f" ]; then
    echo "ERROR: fixture missing: $f" >&2
    exit 2
  fi
done

# 3. Clean start (keep the postgres volume so repeated runs are cheap)
docker compose down 2>/dev/null || true
docker compose up -d postgres

# 4. Wait for postgres
echo "Waiting for postgres..."
if ! wait_for 60 docker compose exec -T postgres pg_isready -U apmatch; then
  echo "ERROR: postgres not ready in 60s" >&2
  docker compose logs postgres --tail=50
  exit 3
fi

# 5. Bring up api
docker compose up -d api

# 6. Wait for healthz
echo "Waiting for api /healthz..."
if ! wait_for 120 curl -fsS http://localhost:8000/healthz; then
  echo "ERROR: api not healthy in 120s" >&2
  docker compose logs api --tail=100
  exit 4
fi
echo "api healthy"

# 6b. Verify the embedding model loads offline inside the container
# (set -e: a non-zero exit fails the smoke test)
echo "Verifying embeddings are online..."
docker compose exec -T api python scripts/verify_offline_embeddings.py

# 7. POST /match
echo "POSTing /match..."
RESPONSE_FILE="$(mktemp)"
HTTP_CODE="$(curl -sS -o "$RESPONSE_FILE" -w '%{http_code}' \
  -X POST \
  -H "X-API-Key: ${APMATCH_API_KEY}" \
  -F "invoice=@${INVOICE}" \
  -F "po=@${PO}" \
  -F "grni=@${GRNI}" \
  -F "pard=@${PARD}" \
  http://localhost:8000/match)" || { echo "ERROR: POST /match failed (curl transport error)" >&2; rm -f "$RESPONSE_FILE"; exit 9; }
RESPONSE="$(cat "$RESPONSE_FILE")"
rm -f "$RESPONSE_FILE"
if [ "$HTTP_CODE" != "200" ]; then
  echo "ERROR: POST /match returned HTTP $HTTP_CODE" >&2
  echo "body: $RESPONSE" >&2
  docker compose logs api --tail=50 >&2
  exit 9
fi

RUN_ID="$(echo "$RESPONSE" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["run_id"])')"
ROUTE="$(echo "$RESPONSE" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["route"])')"
INVOICE_NUM="$(echo "$RESPONSE" | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("invoice_number") or "")')"

echo "  run_id:        $RUN_ID"
echo "  route:         $ROUTE"
echo "  invoice_number: $INVOICE_NUM"

if [ -z "$RUN_ID" ] || [ ${#RUN_ID} -ne 32 ]; then
  echo "ERROR: run_id not a 32-char hex string: $RUN_ID" >&2
  exit 5
fi

if [ "$ROUTE" != "AUTO_APPROVE" ] && [ "$ROUTE" != "HUMAN_REVIEW" ]; then
  echo "ERROR: unexpected route: $ROUTE" >&2
  exit 6
fi

if [ "$INVOICE_NUM" != "INV-2026-1123" ]; then
  echo "ERROR: unexpected invoice_number: $INVOICE_NUM" >&2
  exit 7
fi

# 8. GET /audit/{run_id}
echo "GET /audit/${RUN_ID}..."
AUDIT="$(curl -fsS -H "X-API-Key: ${APMATCH_API_KEY}" \
  "http://localhost:8000/audit/${RUN_ID}")"
AUDIT_ROUTE="$(echo "$AUDIT" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["route"])')"
if [ "$AUDIT_ROUTE" != "$ROUTE" ]; then
  echo "ERROR: audit route ($AUDIT_ROUTE) != response route ($ROUTE)" >&2
  exit 8
fi

# 9. GET /kpis/routes
echo "GET /kpis/routes..."
ROUTES="$(curl -fsS -H "X-API-Key: ${APMATCH_API_KEY}" \
  "http://localhost:8000/kpis/routes")"
echo "  $ROUTES"

# 10. Teardown
docker compose down
echo "SMOKE OK"
