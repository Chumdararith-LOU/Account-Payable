# CI workflows

- `ci.yml` is a **stub**. It will not run until the repository is pushed to a
  GitHub remote and CI is enabled (D-063).
- The `smoke` job requires `APMATCH_API_KEY` to be set as a **repository
  secret** (Settings → Secrets and variables → Actions) before it can run.
- The `smoke` job runs on `ubuntu-latest` (real amd64 hardware) — the correct
  home for the full-stack smoke test, which cannot run under QEMU on Apple
  Silicon (D-062).
- Local dev on Apple Silicon should **not** attempt to run the smoke test —
  `pytest tests/smoke/` skips it cleanly with a clear reason, even when
  `APMATCH_RUN_SMOKE=1` is set.
