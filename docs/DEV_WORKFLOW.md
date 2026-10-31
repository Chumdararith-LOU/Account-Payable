# Dev workflow — edit on the Mac, compute on the server

## Overview
Source of truth: the Mac. Compute: the server.
opencode runs on the Mac and edits files locally. Before any
test, build, or Python/ruff/docker command, a wrapper pushes the
committed state to GitHub, pulls it on the server, and runs the
command there. **Uncommitted local changes do not flow** — commit
first (git is the transport; rsync was retired 2026-10-31).

## Prerequisites
- SSH key auth to `rith@100.88.94.91` (no password prompt).
- The server has `/opt/apmatch` (production deploy) and
  `/home/rith/apmatch-dev` (dev mirror, a git clone of the GitHub
  repo; `git pull` brings it current). Untracked extras (batch data
  under `documents/`, `.env.server`, `reports/`, `output/`) live only
  on the server and are preserved across pulls.
- Both directories have a `.env.server` file with real values.
- The `apmatch:dev` image is built on the server.
- A dedicated **test database** `apmatch_test` exists in the
  server's Postgres. Tests NEVER run against the production
  `apmatch` DB (they assume a clean `audit_log`). One-time setup:

      docker exec apmatch-postgres psql -U apmatch \
        -c "CREATE DATABASE apmatch_test"

  The `pg_engine` fixture runs `alembic upgrade head` on first
  use, so no further schema setup is needed.

## Common commands
Run matching tests:

    ./scripts/remote_pytest.sh tests/matching/ -v

Run the full suite:

    ./scripts/remote_pytest.sh tests/ -q

Run ruff:

    ./scripts/remote.sh 'ruff check apmatch/ tests/ scripts/'

Run a Python script:

    ./scripts/remote.sh 'python scripts/diagnose_match_failure.py'

Sync only (no command):

    ./scripts/remote_sync.sh

Notes:
- `remote.sh` auto-installs ruff (pinned to the Mac's version)
  into the one-off container when the command starts with
  `ruff` — the image only installs `requirements.txt`, and the
  container runs non-root, so the install goes to
  `/tmp/ruffpkgs` and is thrown away with the container.
- `ruff.toml` is mounted into the container by the dev overlay;
  without it ruff would run with default rules and report a
  different (wrong) error count.

## Long-running commands (OCR, full suite)
The server CPU is much slower than the Mac for OCR work, and
local tool timeouts kill foreground SSH sessions. For runs
expected to take more than ~10 minutes, detach **on the
server side** so the run survives local disconnects:

    ./scripts/remote_sync.sh
    ssh rith@100.88.94.91 'cd /home/rith/apmatch-dev && \
      nohup docker compose -f docker-compose.yml \
        -f docker-compose.server.yml -f docker-compose.dev.yml \
        --env-file .env.server \
        run --rm -T --entrypoint /opt/venv/bin/python \
        api -m pytest tests/ -q > /tmp/apm_full.log 2>&1 & \
      echo started'

Then poll the log:

    ssh rith@100.88.94.91 'tail -5 /tmp/apm_full.log'

Memory: the server has 15 GiB RAM and the production API holds
~4 GiB of it. The OCR test container needs ~5 GiB. The full
suite has OOM-killed before when both ran at once — if a run
dies mid-suite with no pytest summary, check
`grep "Out of memory" /var/log/syslog` before assuming a test
failure.

## What does NOT move to the server
- Editing files (opencode does this on the Mac)
- git commit (Mac is authoritative)
- LLM inference (opencode's local model stays on the Mac)

## When to run locally anyway
- Very fast tests (<2 seconds): matching, validation, schema,
  scoring — the sync overhead (~3–5 seconds) exceeds the test
  runtime. Judgment call; document in the task if you bypass.
- Anything that touches the server's Postgres directly

## Environment variables
- `APMATCH_SERVER`      default `rith@100.88.94.91`
- `APMATCH_REMOTE_DEV`  default `/home/rith/apmatch-dev`
