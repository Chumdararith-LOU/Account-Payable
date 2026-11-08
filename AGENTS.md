# AGENTS.md — operating rules for any agent working in this repo

## Hard rules (do not violate)
- A generative model may only EXTRACT (apmatch/parse/vlm.py, D-109). It never
  decides: validation, matching, scoring and routing stay pure code with no
  model calls (enforced by the tests/*/test_no_llm.py guards).
- No external network calls at runtime. The only allowed call is to the local
  VLM server (VLM_BASE_URL).
- All money arithmetic uses `decimal.Decimal`. Never `float` for currency.
- Every new module ships with a matching test file under `tests/`.
- If a version in `requirements.txt` is unavailable, STOP and report.
  Never substitute a different package or version silently.
- Do not `git add -A` after the initial baseline commit. Stage only
  the files the current task names.
- Do not commit `.env`, `*.db`, `.venv/`, or anything in `.gitignore`.

## Environment
- Python env: `anpr` (conda). Activate with `conda activate anpr`.
- Python version: 3.12.13. Do not use the system `python3` (3.9.6).
- All commands in a task run inside this env unless stated otherwise.

## Command execution (updated 2026-10-11)
As of EMB-01e, all pytest / ruff / python / docker commands in
task packets are expected to run on the server via the wrappers:

    ./scripts/remote_pytest.sh [pytest args]
    ./scripts/remote.sh '<command>'

Editing files happens locally (opencode on the Mac). git
commits happen locally. The Mac is the source of truth; the
server is a compute target. See docs/DEV_WORKFLOW.md for the
full workflow, including the server-side detach pattern for
long-running (OCR) commands and the `apmatch_test` database
that tests use (never the production `apmatch` DB).

Exceptions (run locally):
- Tasks that explicitly say "run locally"
- Fast tests (<5s) where the sync overhead is not worth it
- Tests that modify the local Mac environment (rare)

## Repo layout (target)
- `apmatch/`   — the production package (Phase 1 onward)
- `tests/`     — pytest suite
- `docs/`      — ARCHITECTURE.md, TASKS.md, DECISIONS.md
- `scripts/`   — one-off utilities (migration, doc generation)
- No legacy code at repo root as of P1-14; the prototype files were
  removed (every capability now lives in `apmatch/` with tests).

## Task workflow
- Read `docs/TASKS.md` at the start of every session.
- Each task ends with exactly one commit (unless the task says otherwise).
- `docs/TASKS.md` records commit references as grep tags of the form
  `(P1-NN)`, not hashes. Hashes become stale when a task's own commit is
  later amended. The commit subject already contains `(P1-NN)`; find a
  task's commit with:
      git log --oneline --grep="(P1-NN)"
  Do NOT write hashes into TASKS.md going forward.
- Report back in EXACTLY this format:
    1. Files created/modified (full paths)
    2. Commands run + RAW output (do not summarize or paraphrase)
    3. Commit hash + message
    4. Anything you were unsure about or stubbed
    5. Any TODO left in code

## Applying a handoff packet (from the planner)
Some tasks arrive as a "handoff packet": a patch file plus numbered steps.
- Apply the patch exactly as given (`git am <file>.patch`). Do not edit,
  reformat, or "improve" the code it contains unless a step says so.
- Run each command exactly as written, in order.
- If a step fails, STOP. Paste the full raw output back. Do not try to fix it.
- Copy result files (reports/*.json) back exactly as produced.
