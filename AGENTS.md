# AGENTS.md — operating rules for any agent working in this repo

## Hard rules (do not violate)
- No generative model anywhere in the decision path. No LLM calls at runtime.
- No external network calls at runtime. The pipeline must run fully offline.
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
