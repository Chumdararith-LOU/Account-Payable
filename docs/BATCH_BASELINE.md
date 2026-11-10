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

## Post-None-guards baseline (PROD-B0.5)

After guarding every None-unsafe arithmetic site in the matching engine — the
two header checks (`engine.py:346` PARD amount, `:359` date ordering) **and**
the line-item quantity checks (`:261`, `:333`) plus the PO amount-implied
multiplication guard (`:288`) — the batch re-runs with **zero crashes**.
Full per-case report: `reports/batch-b0.5-20261029.json`.

- Total: 120 · Passed: 61 · Failed: 59 · **Rate: 50.8%**
- **Hard errors: 0** (was 99 at PROD-B0)
- Duration: 29.6 min on GPU · Per-case average: 14.8 s

### By style
| Style | Passed | Total | Rate  |
|-------|--------|-------|-------|
| kh    | 17     | 40    | 42.5% |
| us    | 21     | 40    | 52.5% |
| in    | 23     | 40    | 57.5% |

### By expected outcome
| Expected     | Passed | Total | Rate  |
|--------------|--------|-------|-------|
| MATCH        | 0      | 54    | 0%    |
| DISCREPANCY  | 61     | 61    | 100%  |
| PENDING INFO | 0      | 5     | 0%    |

### Failure categories (the 59 failures)
1. **MISSING_REQUIRED_FIELD (blocker): 48 cases** — e.g. `CASE-0005`. OCR did
   not extract a required field on the noisy document; validation blocks →
   REJECT. This is the dominant lever for template work.
2. **LINE_AMOUNT_MISMATCH (blocker): 10 cases** — e.g. `CASE-0001`. Line-item
   amount beyond tolerance → REJECT.
3. **LINE_AMOUNT_MISMATCH (warning): 1 case** — `CASE-0004` (MATCH→HUMAN_REVIEW).

### Interpretation
**This is the honest baseline** that template work (PROD-B1+) is measured
against: **61/120 (50.8%)**, crash-free. The pass rate is entirely carried by
DISCREPANCY cases (61/61 = 100%): a discrepancy correctly routes to
REJECT/HUMAN_REVIEW, which is the expected outcome. Every MATCH case (54) and
PENDING INFO case (5) currently fails — almost all to a `MISSING_REQUIRED_FIELD`
validation blocker (48 of 59), i.e. OCR is not extracting a required field on
the noisy document, so the pipeline rejects instead of auto-approving. The
trajectory is now meaningful and monotonic: PROD-B0 = 5.8% (crash-dominated) →
header guards = 35.8% → all guards = 50.8%. Template work that improves field
extraction attacks the 48 `MISSING_REQUIRED_FIELD` failures directly; closing
most of them would lift the rate toward ~90%.

## Post-header-templates (PROD-B1a)

After externalizing header extraction into per-style YAML templates
(`templates/{kh,us,in,generic}.yaml`) plus candidate-validated value lookup and
the top-company-suffix vendor heuristic, the batch re-runs. Full per-case
report: `reports/batch-b1a-20261029.json`.

- Total: 120 · Passed: 61 · Failed: 59 · **Rate: 50.8%** (unchanged)
- **Hard errors: 0**
- By style: kh 17/40 · us 21/40 · in 23/40 (all unchanged)

### The templates work — but they are not the bottleneck

The header extraction genuinely improved. Per-case `MISSING_REQUIRED_FIELD`
counts on us/in cases dropped **1025 → 955 (−70)**, and `VENDOR_MISMATCH`
dropped **82 → 62** (the vendor heuristic resolves unlabeled sellers). The
selector picks the right style for each document and the kh fixture still
extracts byte-for-byte (regression guard green).

**Yet 0 of the 120 cases changed pass/fail status.** The reason: the us/in
MATCH cases that carry missing-field failures *also* carry line-item matching
failures, so removing the missing-field blocker does not unblock the route.
The dominant non-missing failures on the still-failing us/in MATCH cases are:

| Failure | Count | Meaning |
|---|---|---|
| NO_MATCHING_GRNI_LINE | 67 | invoice line has no matching GRNI line |
| NO_MATCHING_PO_LINE | 66 | invoice line has no matching PO line |
| QTY_MISMATCH | 25 | quantity differs beyond tolerance |
| VENDOR_MISMATCH | 24 | vendor name differs across documents |
| PARD_AMOUNT_MISMATCH | 15 | PARD amount ≠ invoice total |
| NO_LINE_ITEMS | 14 | table parse returned no lines |
| LINE_AMOUNT_MISMATCH | 11 | line amount differs beyond tolerance |

### Interpretation

The PROD-B0.6 diagnostic was right that header labels were a real gap, but it
was **optimistic about the payoff**: it counted the 48 `MISSING_REQUIRED_FIELD`
failures as the lever, without noting that those same cases also fail the
line-item match. The header fix is necessary but not sufficient. The real
bottleneck is **line-item alignment** — the same class of problem as the kh
puzzle (descriptions OCR-garbled → the description-keyed matcher misaligns
lines → `NO_MATCHING_*` / `QTY_MISMATCH` / `LINE_AMOUNT_MISMATCH`). This is
**PROD-B1b** scope (line-item diagnostic + fix), not header scope.

**Consequence for the roadmap:** the pass rate is flat at 50.8% after
PROD-B1a. The trajectory is still monotonic (it did not regress), but the next
gain requires fixing line-item alignment, not adding more header labels.
PROD-B1b should re-run the batch after the line-item fix; that is where the
rate is expected to climb.

## Post-line-item + header fix (PROD-B1c)

After the line-item table-parser fix (D-105: header-driven column mapping +
text-block fallback + completeness-score pick) and the header spatial/vendor
fixes (D-106: widened the invoice number/date label→value gap to 400px; D-107:
vendor heuristic matches business-type nouns), the batch re-runs. Full per-case
report: `reports/batch-b1c-20261030.json`.

- Total: 120 · Passed: 67 · Failed: 53 · **Rate: 55.8%** (was 50.8% at PROD-B1a)
- **Hard errors: 0**
- By style: kh 19/40 (47.5%) · us 25/40 (62.5%) · in 23/40 (57.5%)
- By expected outcome: DISCREPANCY 61/61 · MATCH 3/54 · PENDING INFO 3/5

### The line-item fix worked; the header fix cut missing-fields sharply

The line-item table-parser fix (D-105) resolved the column mis-identification
that PROD-B1b traced: line-item `MISSING_REQUIRED_FIELD` dropped from ~600 to
115, and `NO_LINE_ITEMS` from 14 to 3. The header fixes (D-106/D-107) cut the
header missing-field blockers sharply:

| Header field     | PROD-B1a | PROD-B1c |
|------------------|----------|----------|
| invoice_date     | 80       | 27       |
| invoice_number   | 35       | 14       |
| vendor_name      | 49       | 9        |

### Interpretation

The pass rate climbed 50.8% → 55.8% (**+4 cases, zero regressions**). The header
extraction genuinely improved, but the pass rate is now capped by **out-of-scope**
issues: line-item `MISSING_REQUIRED_FIELD` (115), `LINE_AMOUNT_MISMATCH` (41), and
`PARD_AMOUNT_MISMATCH` (22). Most cases whose header was fixed *also* carry one of
these, so fixing the header alone does not unblock the route. 8 failing cases carry
*only* header blockers (5 us `invoice_date`, 3 `vendor_name`) that the widened gap
and business-type nouns did not reach — a different layout (value further than 400px,
or a vendor name with no business-type word).

**Consequence for the roadmap:** the remaining failures need (a) those 8 residual
header cases and (b) the line-item/matching alignment issues. Both are **PROD-B1d**
scope (template application to PO/GRN/PARD, vendor buyer-rejection, positional-
fallback iteration, and the matching-engine alignment fixes). The trajectory is
monotonic: PROD-B0 = 5.8% → B0.5 = 50.8% → B1a = 50.8% → **B1c = 55.8%**.

## VLM extraction, 200-case batch (PROD-B3 / PROD-B4)

A newer labeled batch (`cases-200`, 4 styles x 50: kh, kh_sme, kh_tax, us)
run with Qwen2.5-VL as the extractor. Report:
`reports/batch-b3-vlm-200.json`. Metrics now include straight-through
(MATCH -> AUTO_APPROVE) and false approvals (non-MATCH -> AUTO_APPROVE),
because routing everything to review already scores 133/200 (D-112).

| Run | Passed | Straight-through | False approvals |
|---|---|---|---|
| PROD-B3 (GPU run, 110 min) | 166/200 | 50/67 | 17 |
| PROD-B4 (offline re-score of the same extractions, no embeddings) | 195/200 | 67/67 | 5 |

PROD-B4 changes (D-113, D-114): 5% price tolerance, partial billing,
tax vs PO rate, PO reference check, receipt-after-invoice, close-name line
join, case-level currency + date reconcile. The 5 remaining false approvals
(CASE-0005, 0068, 0074, 0086, 0110) show no difference in the extracted data;
their planted discrepancy must be identified from the batch labels.
Target (scaled from 100/120): >= 167/200 with 0 false approvals.

### PROD-B4 real runs and the scope change (PROD-B5)

| Batch | Passed | Straight-through | False approvals |
|---|---|---|---|
| cases-200, B4 (cache re-score, embeddings on) | 195/200 | 67/67 | 5 |
| old batch-120 (kh/us/in), B4 VLM run | 99/120 | 35/54 | 1 |

17 of the old batch's 21 failures were Indian GST invoices. India is out of
scope (D-115), so the accuracy test is now the two USD/KHR batches:
`cases-200` and `batch-usd-khr-120`. On the old batch, kh is 40/40 and us
38/40 after PROD-B5 (offline re-score).

## PROD-B6 — both USD/KHR batches pass (2026-11-10)

| Batch | Passed | Straight-through | False approvals | Run |
|---|---|---|---|---|
| batch-usd-khr-120 | 120/120 | 43/43 | 0 | 38 min (invoices + POs re-read) |
| cases-200 | 200/200 | 67/67 | 0 | 63 min (invoices + POs re-read) |

Reports: `reports/batch-b6-vlm-usdkhr-120.json`, `reports/batch-b6-vlm-200.json`.
Answer keys: `reports/labels/`. Caught for the planted reason (checked against
the answer keys' scenario column): 76/77 and 130/133 discrepancy/pending cases;
the other 4 are still routed to review/reject, but by a neighbouring check
(e.g. an extra invoice line joined to the wrong PO line shows as a price
mismatch instead of "no matching PO line").

Trajectory on the accuracy test: old OCR pipeline 55.8% (old 120 batch, B1c)
-> Qwen B3 83% -> B4 97.5% -> B6 100% on both USD/KHR batches.

Caveat: the B4-B6 rules were written while looking at these two batches and
their answer keys. 100% here shows the rules are implemented correctly; it is
not yet an independent accuracy estimate. Measure next on a batch neither the
rules nor the prompts have seen (ideally real customer documents).
