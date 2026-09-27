# ARCHITECTURE.md — factual snapshot (P1-01)

## Pipeline summary

Document image → OCR (PaddleOCR PP-Structure, currently run externally) → JSON
(`text_blocks` with bboxes + `tables` as HTML) → field extraction (regex +
spatial bbox heuristics in `database.py`) → SQLite (`ap_automation.db`) →
3/4-way match engine (`ai_engine.py`: PO / GRNI / Invoice / PARD) → outcome
MATCH / DISCREPANCY / PENDING INFO with a 0–1 confidence score → Streamlit
dashboard + FastAPI service.

## Current state — prototype files

| File | Role |
|---|---|
| `database.py` | SQLite layer: schema (8 tables), insert fns, JSON→field extractors, spatial OCR helper `get_text_below_label`, JSON→DB migration, dashboard stats |
| `ai_engine.py` | Matching engine: vendor lookup, line-item join via OCR-noise normalization, qty/price/payment rules, scoring, MATCH_RESULT writes |
| `pp.py` | Document-processing dispatcher: doc_type routing, invoice duplicate check, `save_match_result` (queue routing commented out) |
| `api.py` | FastAPI service v1.1: `/health`, `/samples`, `/stats`, `/process`, `/process-direct`, `/process-file`; API-key auth; embedded demo HTML page |
| `dashboard.py` | Streamlit KPI dashboard: metric cards, top-discrepancy bar chart (Plotly), processing log table |
| `generate_test_docs.py` | Generates bilingual EN/Khmer test docs (PO/GRNI/INV/PARD) as PDF+PNG via WeasyPrint + pdftoppm |
| `apmatch/ocr/engine.py` | `LatinOCREngine` — deterministic, offline, CPU-only wrapper around PaddleOCR 3.7.0 (PP-OCRv6_medium det/rec) for Latin/numeric text; returns `OCRResult` (frozen dataclasses, incl. optional `tables: tuple[Table, ...]`) and `to_prototype_json()` matching the `output/ocr/*.json` schema |
| `apmatch/ocr/khmer.py` | `KhmerOCREngine` — deterministic, offline, CPU-only wrapper around TrorYongOCR (tror-yong-ocr 0.2.7) for Khmer-script text; recognition-only (no detection), operates on cropped single-line regions, returns the same `OCRResult` schema with bbox = (0, 0, w, h) of the crop |
| `apmatch/layout/structure.py` | `LayoutEngine` — deterministic, offline, CPU-only wrapper around PaddleOCR 3.7.0 PP-StructureV3 for table extraction; returns `tuple[Table, ...]` (`Table` dataclass: html + bbox + page_index) and `to_prototype_json()` matching the prototype's `tables` schema (single `html` key). Called independently of the OCR router |
| `apmatch/schema/documents.py` | Frozen dataclasses `Invoice`, `PurchaseOrder`, `GRNI`, `PaymentAdvice`, `LineItem` — the canonical in-memory AP document contract; every monetary field is `Decimal` |
| `apmatch/schema/coercion.py` | `to_money` / `to_unit_price` / `to_qty` — the single boundary that turns external numeric input into quantized `Decimal`; rejects `float` with `TypeError` |
| `apmatch/validation/result.py` | `Severity`, `CheckCode` (enum), `CheckFailure`, `ValidationResult` — the structured validation outcome (code + severity, never free text) |
| `apmatch/validation/arithmetic.py` | Pure functions `validate_invoice` / `validate_po` / `validate_grni` / `validate_pard` — internal arithmetic-consistency checks; no I/O, no exceptions for business failures; plus a CLI |
| `apmatch/matching/config.py` | Tolerance + matching constants (all money as `Decimal`), `MATCHABLE_FIELDS`; constants not config files |
| `apmatch/matching/normalize.py` | Pure `normalize_text` / `normalize_number_text` / `normalize_currency` — OCR-noise stripping tuned to keep meaning |
| `apmatch/matching/result.py` | `Outcome`, `MatchCode` (12 codes), `MatchFailure`, `MatchResult` — the structured match outcome (code + severity, never free text); `failures` ordered by (severity desc, code asc, location asc) |
| `apmatch/matching/engine.py` | `MatchingEngine.match(invoice, po, grni, pard) -> MatchResult` — deterministic 4-way match (vendor/currency/line/PARD/date); pure, no I/O, no LLM; plus a CLI that reads four JSON files and prints the result |

`LatinOCREngine` wraps PaddleOCR 3.7.0 PP-OCRv6_medium; `LayoutEngine` wraps
PP-StructureV3. Model weights are vendored at `models/paddleocr/` (gitignored,
14 model dirs, ~1.2 GB) and pointed at via the constructors' `*_model_dir`
kwargs; offline env vars (`PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True`,
`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`) are set inside `__init__` before
the paddleocr import. One-time provisioning of the vendored cache:
`cp -R ~/.paddlex/official_models/. models/paddleocr/`. Zero-network runtime
is proven by `scripts/verify_offline.py` + `tests/ocr/test_offline.py` (OCR)
and `scripts/verify_offline_structure.py` +
`tests/layout/test_structure_offline.py` (tables), both with socket.connect
blocked.

Supporting: `migrate_to_db.py` (one-shot JSON→SQLite), `generate_report.py`
(static HTML completion report), `set_api_key_visible.py` (writes `.env`),
`Plan.md` (proposal), `report.md` (P1-00 recon).

## Document schema contract

The in-memory AP document model (`apmatch/schema/`) is the contract every
downstream module (validation, matching, remarks, audit) consumes:

- **Frozen dataclasses, Decimal-only money.** `Invoice`, `PurchaseOrder`,
  `GRNI`, `PaymentAdvice`, `LineItem` are `@dataclass(frozen=True)`. Every
  monetary field is a `decimal.Decimal` (never `float`). The field sets mirror
  the legacy SQLite schema in `database.py`, extended with the richer contract
  fields the matching engine needs.
- **Float rejection at the coercion boundary.** `apmatch/schema/coercion.py`
  (`to_money` / `to_unit_price` / `to_qty`) is the single place external
  numeric input becomes a quantized `Decimal`. It raises `TypeError` on any
  `float`, so a float can never silently enter the money path.
- **ValidationResult carries code + severity, never free text.** Failures are
  `CheckFailure(code: CheckCode, severity: Severity, ...)`. Downstream modules
  switch on `CheckCode`; they must never string-match a message. New failure
  modes are added by extending `CheckCode`, not by inventing message strings.
- **Failure ordering is part of the contract.** `checks_failed` is sorted by
  (severity desc, then code asc, then location asc). Tests assert this order.
- **`tax_rate` / `discount_rate` are OPTIONAL fractions** (`0.10` = 10%, not a
  percentage). When present, `TAX_MISMATCH` / `DISCOUNT_MISMATCH` is a real
  arithmetic check (BLOCKER). When absent, those checks are sanity-only and
  emit WARNING severity with a `"sanity-only"` location tag.
- **DB-only metadata (`created_at`) is not part of the schema.** Row insert
  timestamps live in the database; read them from there if needed.
  - Remarks are generated by `apmatch/remarks/templates.py`, a pure-Python
    template module. No generative model participates in remark generation.
    Every `CheckCode` maps to exactly one template; coverage is enforced by
    `tests/remarks/test_templates.py::test_all_checkcodes_have_template` and
    `tests/remarks/test_no_llm.py`.
  - Matching primitives (config constants, text normalization) live under
   `apmatch/matching/`. Tolerances are Python constants, not config files;
   changes require a task and updated tests. OCR-noise stripping is heuristic
   and errs toward keeping content.

## Matching engine contract

`apmatch/matching/engine.py` is pure: no I/O, no LLM, no network. It consumes
the schema dataclasses and returns a `MatchResult`.

- **Three-valued outcome.** `MATCH` (zero failures), `DISCREPANCY` (any
  failure, blocker or not), `PENDING_INFO` (a required document is missing).
  The blocker distinction is carried by `MatchResult.has_blocker`, not the
  outcome.
- **Missing documents short-circuit.** A missing PO / GRNI / PARD returns
  `PENDING_INFO` with score `0.0` and a single `*_MISSING` failure before any
  other check runs.
- **Score model.** Starts at `1.0`; each `MatchFailure` subtracts
  `config.MATCH_CODE_WEIGHTS[code]`; the result is clamped to `[0.0, 1.0]`.
  Weights are `Decimal` constants, not config files.
- **Line join.** Invoice lines are matched to PO / GRNI lines on
  `normalize_text(description)`, first match in source order. Quantity must
  match exactly; unit price and line amount use the absolute-OR-relative
  tolerance (pass if `abs diff <= ABS` or `abs diff / max <= REL`).
- **Currency check.** `CURRENCY_MISMATCH` fires only when both
  `invoice.currency` and the counterpart document's currency (PO and/or PARD)
  are populated and differ after `normalize_currency`. Missing currency on
  either side skips the check (no false positive). PO and PARD are checked
  independently, so both can fail at once (D-024).
- **Failure ordering is part of the contract.** `failures` is sorted by
  (severity desc, then code asc, then location asc), mirroring
  `apmatch.validation.result`.

## Target state (Phase 1) — workstreams

See `docs/TASKS.md` for status. The 13 Phase 1 workstreams:

| ID | Workstream |
|---|---|
| P1-02 | Upgrade Paddle stack (paddleocr 3.7.0 / paddlepaddle 3.3.1) |
| P1-03 | OCR engine wrapper (Latin/numeric) — PP-OCRv6 |
| P1-04 | Script router + Khmer module |
| P1-05 | Layout/table structuring — PP-StructureV3 |
| P1-06 | Arithmetic validation layer |
| P1-07 | Template remark module (replaces LLM remarks) |
| P1-08 | Matching engine hardening |
| P1-09 | Confidence scoring & routing |
| P1-10 | Storage: SQLite → PostgreSQL |
| P1-11 | Audit log + dashboard hooks |
| P1-12 | Docker + REST API |
| P1-13 | Bilingual test corpus + goldens |

(P1-00 recon and P1-01 repo baseline are the enabling tasks.)

## Known issues

- `.venv` was broken (created on another machine; shebangs pointed at
  `/home/admin-ubuntu/`) and was removed in P1-01. Phase 1 uses the `anpr`
  conda env.
- No requirements manifest existed; P1-01 adds `requirements.txt` (target
  pins, not yet installed).
- API key hardcoded in `api.py` (`DPAI-DEMO-2026`).
- `PRICE_TOLERANCE = 0.01` in `ai_engine.py` is commented "1%" but the
  proposal (Plan.md §5) says ±5% — code/comment drift.
- LLM/generative code fully removed (P1-02, D-005). Template remark module
  lands in P1-07.
- The legacy root-level prototype files contain no OCR invocation code; the
  OCR JSONs in `output/ocr/` were produced externally. In-repo OCR now lives
  in `apmatch/ocr/engine.py` (P1-03).
- `cloudflared-linux-amd64` is a Linux binary, unusable on this macOS host.
- `tror-yong-ocr` is installed in `anpr` but unaudited (audit performed in
  P1-01 step 11; see report).
- Khmer OCR does not integrate with PP-OCRv6's detector yet — router lands
  in P1-04b.
- `KhmerOCREngine.recognize()` operates on cropped regions only (tror-yong-ocr
  has no text detection); routing by region is P1-04b's responsibility.
- Third-party bug in tror-yong-ocr 0.2.7: MultiheadAttention.forward
  passes dropout_p=0.1 into F.scaled_dot_product_attention even in
  eval mode, making recognition non-deterministic across calls and
  processes. Worked around in apmatch/ocr/khmer.py by model.eval()
  plus zeroing every dropout module's `p`. Regression-guarded by
  tests/ocr/test_khmer_dropout_fix.py. If upstream releases a fix,
  revisit and remove the workaround.
- Khmer engine output is not script-strict — a single text block may mix
  Khmer and Latin characters (e.g. `( Whiteboard ) ក្តារខៀន`). Downstream
  field extractors (P1-08+) must not assume single-script blocks.
- PP-StructureV3 found 1 table on the bilingual invoice INV_2026_1123.png,
  matching the prototype reference (`output/ocr/INV_2026_1123.json` also
  carries 1 table). If future fixtures diverge, note that PP-StructureV3 and
  the older prototype pipeline differ in table detection thresholds; P1-13's
  corpus work will reconcile.
- PP-StructureV3 formula/seal/chart recognition is disabled at construction
  (`use_formula_recognition=False`, `use_seal_recognition=False`,
  `use_chart_recognition=False` in `LayoutEngine.__init__`); AP invoices
  contain none of these. The PP-FormulaNet_plus-L weights (~702 MB) were
  removed from `models/paddleocr/` (P1-05b); the vendored cache is now
  ~1.2 GB.
- opencv-contrib-python pinned to 4.10.0.84 by paddlex, overriding the
  previous 4.11.0.86 — verify ultralytics still imports (checked in P1-03,
  see F.4 result in the P1-03 report).
