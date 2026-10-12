# Cross-Environment Determinism Report

Measured 2026-10-12 (EMB-01g). Evidence for the bank conversation: how much
does the pipeline's output diverge when the same documents are processed on
the Mac dev environment vs the production server?

## Environment

- Mac:    PaddlePaddle 3.3.1, Python 3.12.13, arm64 (Apple Silicon)
- Server: PaddlePaddle 3.2.2, Python 3.12.15, amd64 (Intel i3-1220P)
- Fixtures: 6 images — the 4 pipeline documents
  (`INV_2026_1123.png`, `PO_2026_0451.png`, `GRN_2026_0322.png`,
  `PARD_2026_0210.png`) plus 2 extra invoices (`invoice.png`,
  `Pasted image.png`) OCR'd for comparison but not fed into the pipeline.

## Method

`scripts/dump_pipeline_output.py` runs the full pipeline (OCR → layout →
parse → validate → match → decide → input hash) on both machines and writes
canonical JSON (sorted keys, Decimals as strings, dates ISO 8601, bbox
rounded to int, confidence rounded to 2 dp). `scripts/compare_environments.sh`
runs both dumps and `scripts/compare_json_dumps.py` produces a structured
diff with tolerances: text exact, bbox ±1 pixel per coordinate, confidence
±0.01. Full diff: `/tmp/determinism_diff.txt` (regenerate with
`./scripts/compare_environments.sh`).

### What "deterministic" means in this report

Two distinct properties:

1. **Single-environment determinism** — with the Paddle version
   and hardware pinned, the same input always produces the same
   output, byte-for-byte. This is what our `input_hash` verifies.
   It is what an auditor on a given deployment can check.

2. **Cross-environment decision parity** — two environments with
   different Paddle versions (or different CPUs) produce the same
   *decision* on the same input. This is what this report
   measures.

The first is a guarantee. The second is an observed property of
the current fixtures, with the divergence numbers given below.

## Findings

### OCR-layer divergence

- Total text blocks compared: 302 (per-image block counts identical on both
  sides: 47/47/42/37/48/81)
- Blocks with identical text: 294 (97.3%)
- Blocks with differing text: 8 (2.7%)
- Blocks differing only in bbox/conf beyond tolerance: 15 (5.0%)
- Tables compared: 6 (per-image counts identical: 1/2/1/1/0/1); 3 differ in
  HTML (invoice, grni, Pasted image)

Sample divergences:

| Image | Block | Mac OCR | Server OCR |
|---|---|---|---|
| invoice | [29] | `Desk ! អញ្ជើញ` | `Desk Lamp ) អំពិល` |
| po | [6] | `ប្រយ័ត្ន` | `Vendor /ñư` |
| grni | [5] | `Received By (Warehouse) / ñsư` | `Delivered By (Vendor) / ñns` (blocks [5]/[6] swapped in order) |
| Pasted image | [66] | `32,250.4` | `₹32,250.4` |
| invoice | [19] | `Description / ưưw` | `Description / ưư` |

The divergences are OCR-noise shaped: garbled header text, different noise
suffixes after slashes, a Khmer/Latin script-routing difference (po [6]), a
detection-order swap (grni [5]/[6]), and a currency-symbol detection
difference (Pasted [66]).

### Extraction-layer divergence

- Documents compared: 4
- Fields differing: 3 — all line-item descriptions (OCR noise):
  - invoice line 1: `Office Chair/nnw` (Mac) vs `Office Chair/nHnw` (server)
  - invoice line 2: `Desk Lamp/i` (Mac) vs `Desk Lamp/` (server)
  - grni line 1: `Office Chair/nmww` (Mac) vs `Office Chair/mww` (server)
- All header fields (document numbers, vendor, dates, currency, subtotal,
  tax, total, PARD amount) are identical on both sides. All three differing
  descriptions normalize to the same value (`office chair`, `desk lamp`).

### Pipeline-level divergence

- Validation results: identical
- Match outcome: identical — `MATCH`, score 1.0000 on both sides
- Routing decision: identical — `AUTO_APPROVE` / `ALL_CHECKS_PASSED`,
  score 1.0000 on both sides
- `input_hash`: DIFFERS (Mac `4d1e6bd3…`, server `7c42b28c…`) — expected:
  the hash is over the parsed documents including the raw (noisy) line-item
  descriptions, which differ. The hash is an input fingerprint, never a
  decision input.

## Interpretation

The OCR layer is not byte-identical across Paddle versions — 2.7% of text
blocks differ in content and 5.0% differ in bbox/confidence beyond tolerance,
and 3 of 6 tables render different HTML. This is expected: different model
weights (3.3.1 vs 3.2.2) and different CPU/oneDNN code paths (arm64 vs amd64)
produce different sub-pixel detections and different noise on low-quality
regions. What matters for the bank conversation is that the divergence is
absorbed before it reaches a decision: the extraction layer differs in only 3
line-item descriptions (all OCR noise that the normalizer maps to the same
canonical value), and the pipeline-level result — validation, match outcome,
score, and routing decision — is identical on both environments. The pipeline
is decision-deterministic across these environments even though it is not
OCR-deterministic.

## Handling plan

The residual OCR-level variation (2.7% of text blocks) does not
propagate to the pipeline decision on the measured fixtures.
This is because normalization in apmatch/matching/normalize.py
collapses the divergent forms to a common canonical string
before matching runs. EMB-02 (embeddings) will further reduce
sensitivity to noise by allowing semantic matches when
normalization does not converge.

The `input_hash` is deliberately scoped to a single environment
(see D-079). It is *not* a cross-environment parity check.

## Additional findings

- **Latent Mac-environment bug**: Paddle 3.3.1 returns
  `cell_box_list` as a numpy array for `Pasted image.png` (a list on
  3.2.2), and `apmatch/layout/structure.py:89` (`if cells:`) raises
  `ValueError` on it. The production 4-document pipeline does not hit this
  (none of the four fixtures triggers the numpy path), but any invoice whose
  table produces a numpy `cell_box_list` would crash on the Mac env. The
  dump script works around it with a runtime shim (no `apmatch/` change in
  this task); a one-line fix (`if len(cells):`) is recommended for a
  future task.
- **GRNI detection-order swap**: the two signature blocks come back in
  opposite order on the two environments. Parsing is unaffected (both
  labels are extracted by label, not position), but it shows detection
  order is not a stable cross-environment contract.
- **Script routing is per-environment**: po [6] is read as Khmer on the Mac
  and as Latin noise on the server (the confidence-triggered Khmer
  re-read makes different choices). Parsing is unaffected.

## Status

- Normalizer regex: extended in EMB-01d and EMB-01f to handle the observed
  pattern classes (all-lowercase, uppercase-start, lowercase-start mixed,
  and trailing-slash noise).
- Residual divergence: documented above (31 total differences: 26 OCR,
  3 field, 2 pipeline [input_hash + paddle version]).
- Cross-environment parity: the pipeline's final decision **is** identical
  across environments for these fixtures (MATCH → AUTO_APPROVE, score 1.0).
