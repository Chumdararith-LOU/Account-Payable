# Demo Rehearsal Log (EMB-13)

Three consecutive end-to-end runs of `scripts/run_demo_case.py` against the
live server (`http://100.88.94.91:8001`, GPU), on the actual demo equipment.
Purpose: prove the demo works when someone is watching.

Similarity scores were **identical across all three runs** (deterministic):
`0.7344, 0.8978, 0.8832, 0.8832, 0.7723, 0.7723` — all in the `accept` band.

## Rehearsal 1 — 2026-10-29 01:05 UTC (cold start)
- Cold start (container restart → healthy): **19s**
- Pipeline (wall clock, incl. SSH key fetch + audit): **24.81s**
- Route: AUTO_APPROVE, score 1.0
- Similarity matches: 6
- run_id: `36a9bcf48f4a4856aa674a5e50534a3f`
- Notes: worst-case demo prep — operator restarts the container, waits ~20s
  for healthz, then runs the case. No manual intervention needed.

## Rehearsal 2 — 2026-10-29 01:08 UTC (warm)
- Pipeline (wall clock): **26.67s**
- Route: AUTO_APPROVE, score 1.0
- Similarity matches: 6 (identical scores to run 1)
- run_id: `6fcc263b2345491aba3730286ef10abf` (new audit row, ≠ run 1)
- Notes: wall time slightly higher than run 1 — variance is in the SSH key
  fetch + network, not the pipeline (the pipeline itself is ~17s on GPU).

## Rehearsal 3 — 2026-10-29 01:11 UTC
- Pipeline (wall clock): **20.94s**
- Route: AUTO_APPROVE, score 1.0
- Similarity matches: 6 (identical scores to runs 1–2)
- run_id: `4264ec5b59224601a935d96d6b36dc59` (new audit row, ≠ runs 1–2)
- Notes: three consecutive runs, no manual intervention.

## Summary
- 3/3 runs: AUTO_APPROVE, score 1.0, 6 similarity matches, identical scores.
- Cold start ~19s; per-run wall clock ~21–27s (pipeline ~17s + key fetch +
  network variance).
- Each run writes a distinct audit row (distinct run_id) — the audit trail
  accumulates as expected.
- **Ready for demo.**
