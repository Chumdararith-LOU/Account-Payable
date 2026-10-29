# Batch baseline — 120 cases (PROD-B0)

The labeled batch (120 cases, 3 styles × 40, 475 images) run through the
production pipeline on the GPU server. This is the measurement instrument for
every template-system change (PROD-B1 through B6): the pass rate must climb
monotonically as templates improve field extraction.

Runner: `scripts/run_batch.py` (stdlib-only, loads OCR/layout/embedding engines
once, `run_pipeline()` per case, no HTTP, no DB). Full per-case report:
`reports/batch-baseline-20261029.json`.

## Summary
- Total: 120 · Passed: 7 · Failed: 113 · **Rate: 5.8%**
- Duration: 29.7 min on GPU · Per-case average: 14.9 s
- **Hard errors (pipeline crashes): 99 (82.5%)** — the pipeline raised instead
  of returning a route. These are counted as failures.

## By style
| Style | Passed | Total | Rate |
|-------|--------|-------|------|
| kh    | 7      | 40    | 17.5% |
| us    | 0      | 40    | 0%    |
| in    | 0      | 40    | 0%    |

## By expected outcome
| Expected     | Passed | Total | Rate  |
|--------------|--------|-------|-------|
| MATCH        | 0      | 54    | 0%    |
| DISCREPANCY  | 7      | 61    | 11.5% |
| PENDING INFO | 0      | 5     | 0%    |

## Failure categories (top 5)
Grouped by first failure / crash type. Counts sum to the 113 failures.

1. **TypeError crash — date compare (date vs None): 60 cases** — e.g. `CASE-0002`
   `apmatch/matching/engine.py:359` — `pard.payment_date < invoice.invoice_date`
   has no None-guard; when OCR returns `None` for either date the engine raises.
2. **TypeError crash — arithmetic (None vs Decimal): 34 cases** — e.g. `CASE-0001`
   `apmatch/matching/engine.py:346` — `abs(pard.amount - invoice.total)` has no
   None-guard; a `None` amount or total raises.
3. **TypeError crash — arithmetic (None vs None): 5 cases** — e.g. `CASE-0008`
   `apmatch/matching/engine.py:346` — both operands `None`.
4. **MISSING_REQUIRED_FIELD (blocker): 7 cases** — e.g. `CASE-0006` (header),
   `CASE-0043` (line 1). A required field was not extracted; validation blocks →
   REJECT.
5. **LINE_AMOUNT_MISMATCH (blocker/warning): 7 cases** — e.g. `CASE-0013` (line 2).
   Line-item amount beyond tolerance → REJECT (or a review-band warning).

## Interpretation
The 5.8% baseline is **crash-dominated, not route-dominated**: 99 of 120 cases
(82.5%) never reach a route because the matching engine crashes on a `None`
header field. The line-item matching is None-safe (explicit `is not None` guards
at `engine.py:272,288`), but the header-level PARD-vs-invoice checks
(`engine.py:346,359`) are not. The 21 cases that *did* produce a route show the
pipeline works when the header fields are extracted: 7 pass (all kh DISCREPANCY)
and 14 fail (MATCH→REJECT/HUMAN_REVIEW, PENDING INFO→REJECT). The kh style
crashes far less (23) than us/in (38 each) — its layout is more OCR-robust for
the header fields.

**Consequence for the roadmap:** the "climbs monotonically with templates"
trajectory is blocked. Templates (PROD-B1+) improve field extraction, but the
matching engine will still crash on any case where a header field is `None`. An
implicit **PROD-B0.5** — None-guards on `engine.py:346,359` (mirroring the
line-item pattern) — must land before PROD-B1+ can be measured. Once the 99
crashes are unmasked into routes, the pass rate will jump substantially and the
trajectory becomes meaningful. This baseline is the starting point of that
trajectory; it is not yet a usable auto-processing-rate claim.
