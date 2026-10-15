# ARCHITECTURE.md — factual snapshot (P1-01)

## Repository layout

- `apmatch/`        — the production package
- `tests/`          — pytest suite (includes `tests/smoke/`)
- `scripts/`        — dev tools (migration, offline verify, smoke test)
- `docs/`           — ARCHITECTURE, DECISIONS, TASKS, OFFLINE_MODELS
- `alembic/`        — database migrations
- `models/`         — vendored model weights (gitignored)
- `documents/`, `test_docs/`, `output/ocr/` — test fixtures
- `Dockerfile`, `docker-compose.yml`, `ruff.toml`,
  `requirements.txt`, `requirements-dev.txt`, `pytest.ini`

There is no legacy code at repo root as of P1-14. The prototype files
(ai_engine.py, database.py, api.py, dashboard.py, pp.py,
remark_generator.py, set_api_key_visible.py, migrate_to_db.py,
generate_report.py, generate_test_docs.py) have been removed. Every
capability they provided lives in apmatch/ with tests.

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
| `apmatch/remarks/matching.py` | `MATCH_TEMPLATES` (one per `MatchCode`), `remark_for_match`, `summarize_match` — deterministic match remarks, parallel to `templates.py`; no LLM; import-time coverage assertion; plus a CLI |
| `tests/integration/` | First end-to-end proof: `test_pipeline.py` runs dataclass → validation → matching → remark on committed JSON fixtures (`fixtures/happy_path`, `fixtures/discrepancy_path`) with no OCR, no DB, no network; a guard test asserts no ML imports leak in |
| `apmatch/scoring/` | `result.py` (`Route`, `RouteReason`, `ConfidenceScore`, `RoutingDecision`), `config.py` (thresholds + weights), `confidence.py` (`validation_component` / `match_component` / `combined_score`), `router.py` (`decide` + CLI) — deterministic confidence score + three-valued routing; no LLM, no I/O, no network |
| `apmatch/store/models.py` | SQLAlchemy 2.x ORM models mirroring the P1-06 dataclasses (7 tables); money/quantity are `Numeric(18,4)`, never Float |
| `docker-compose.yml` | Local dev Postgres 16 on port 5433 (dev-only credentials); `alembic/` + `alembic.ini` hold the migrations |
| `apmatch/audit/` | `entry.py` (`AuditEntry`), `hashing.py` (`compute_input_hash`), `models.py` (`audit_log`), `repository.py` (`AuditRepository`) — append-only audit log with SHA-256 input hashing; no FKs, no update/delete/upsert |
| `apmatch/parse/` | Deterministic OCR-to-dataclass extraction layer: `spatial.py` (bbox primitives), `coerce.py` (noisy-string parsers), `_table.py` (table-HTML rows), `_common.py` (shared label/vendor/total heuristics), `invoice.py` / `purchase_order.py` / `grni.py` / `payment_advice.py` (extractors + CLIs), `dispatch.py` (`DocumentKind` + `extract`) |
| `apmatch/api/` | FastAPI HTTP API: `config.py` (env-driven, fail-fast), `schemas.py` (Pydantic response models), `pipeline.py` (`run_pipeline` — OCR→parse→validate→match→score→audit entry, no DB write), `app.py` (lifespan, `X-API-Key` auth, `/healthz` `/match` `/audit/{run_id}` `/kpis/routes` `/kpis/recent`, enum-coded errors) |

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
- **Validators handle None fields gracefully.** The extraction layer is total
  (D-042) — it returns `None` for any field it could not read, even one that is
  nominally required in the schema. The validators therefore never raise for a
  missing value: a missing required field produces `MISSING_REQUIRED_FIELD`
  (BLOCKER), and the arithmetic checks that depend on it are skipped, not
  attempted. A document with two missing fields emits exactly two
  `MISSING_REQUIRED_FIELD` failures — no double-reporting, no cascading
  arithmetic failures.
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

## Extraction layer

`apmatch/parse/` consumes an `OCRResult` (`text_blocks` + `tables`, from
P1-03/04/05) plus a document-kind hint and produces the corresponding P1-06
schema dataclass. It replaces the legacy `database.py` extractors (kept
read-only as reference; not imported).

- **Deterministic.** Same `OCRResult` → same dataclass, always. No ML, no
  randomness, no wall-clock dependence.
- **Total functions.** Given ANY `OCRResult` (including empty), an extractor
  returns a dataclass. It never raises for a missing field — undetermined
  fields are `None` (or a documented default, e.g. currency `"USD"`). The
  validator (P1-06) is the sole authority on what counts as a blocker.
- **Derivation policy matches P1-10c-fix.** Preserve explicit source values;
  derive implicit ones when absent (subtotal from line amounts, total from
  subtotal + tax).
- **Table columns are located by header text** (case-insensitive substring),
  robust to column reordering, with a positional fallback when no header row
  is present. Footer rows (`colspan`) are skipped.
- **Label lookup is spatial + same-block.** `find_label` matches label
  variants (casefolded substring, first match in source order); the value is
  then read from the label block's own text (PP-OCRv6 merges label and value,
  e.g. `No.:INV-2026-1123`), then from blocks to the right, then below.
  Same-block remainders must contain a digit, so OCR noise tails (`/H`,
  `/NJU`) fall through to the spatial lookup.
- **No-LLM guard.** `tests/parse/test_no_llm.py` AST-walks the package and
  fails on any LLM/network import, with a /tmp sanity check proving the
  walker catches a synthetic bad import.

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
- **Match remarks.** Generated by `apmatch/remarks/matching.py` using the same
  discipline as validation remarks. No generative model. Coverage enforced by
  `tests/remarks/test_matching_templates.py::test_all_matchcodes_have_template`.
 - **End-to-end proof.** `tests/integration/test_pipeline.py` runs the full
   deterministic chain (dataclass → validation → matching → remark) with no OCR,
   no database, no network, and includes a guard test that asserts no ML imports
   leak into the integration layer.

## Scoring & routing contract

`apmatch/scoring/` is pure: no I/O, no LLM, no network. It consumes a
`ValidationResult` and `MatchResult` (plus an optional OCR confidence) and
produces a `ConfidenceScore` and a `RoutingDecision`.

- **Scoring.** Combines validation + matching (+ optional OCR confidence) with
  configurable weights. All weights are Python constants; changing them is a
  task, not a config edit. When OCR confidence is absent, the validation/match
  weights are renormalized to sum to 1.0 so a missing signal does not depress
  the score.
- **Routing is deterministic and follows a fixed order:** REJECT (validation
  blocker) → HUMAN_REVIEW (any of: match not-MATCH, low OCR confidence, low
  overall score) → AUTO_APPROVE.
- **`RouteReason` is enum-coded.** Reviewers read the underlying
  `ValidationResult` / `MatchResult` for detail, not free text.
 - **No LLM, no network in `apmatch/scoring/`;** enforced by
   `tests/scoring/test_no_llm.py`.

## Storage

Postgres 16, SQLAlchemy 2.x, Alembic.

- **Money columns are `NUMERIC(18,4)`.** Float is forbidden by schema test
  (`tests/store/test_schema.py::test_no_float_or_real_columns`).
- **Local dev Postgres** runs via `docker compose up -d postgres` (port 5433).
  Dev credentials are in `docker-compose.yml` and are NOT production
  credentials.
- **Production credentials** come from env vars at runtime (P1-12).
- **Repositories** in `apmatch/store/repositories.py` expose
  `save`/`load`/`exists`/`delete` per document kind. The public API takes and
  returns P1-06 dataclasses; ORM instances never cross the boundary.
- **Round-trip guarantee:** `load(save(x)) == x` for every document kind,
  Decimal-precision-exact. Enforced by `tests/store/test_repositories.py`.
- **The caller manages transactions;** repositories never commit (they flush so
  a same-transaction `load` can see saved rows).
- **Legacy SQLite migration** was a one-shot DEV-ONLY step (P1-10c); the
  script and its fixture DB were removed at P1-14. Production schema changes
  go through Alembic.

## Audit log

Append-only. Exactly one row per pipeline run.

- **No foreign keys** to document tables — the audit record must survive
  document deletion.
- **`input_hash`** is SHA-256 over canonical JSON of the four documents; same
  inputs → same hash, byte-for-byte, across processes.
- **Failure tuples** stored as JSONB arrays of structured fields; never
  pre-rendered strings.
- The repository provides `append`/`get`/`list_recent` only. `update`/`delete`/
  `upsert` are absent by design.
- Read-only KPI queries live in `apmatch/audit/kpis.py`. Aggregates are
  computed by Postgres; functions return bounded dataclasses, never iterators
  or ORM instances. No caching today; correctness over throughput.

## HTTP API

`apmatch/api/` is the first surface a bank integrates against. It wires the
full deterministic pipeline behind a small FastAPI app:

- **`POST /match`** — up to four image uploads (invoice required; po/grni/pard
  optional) → OCR → parse → validate → match → score → one `audit_log` row →
  the routing decision. Sync on purpose: the OCR pipeline is blocking, so
  FastAPI runs it in its threadpool.
- **`GET /audit/{run_id}`** — the stored decision for a run.
- **`GET /kpis/routes`** / **`GET /kpis/recent`** — read-only KPI queries over
  the audit log.
- **`GET /healthz`** — no auth; liveness for the load balancer.

Design notes (see D-051/D-052):

- **Config** is plain module vars in `config.py`, read at import and fail-fast
  (no default API key). No pydantic-settings dependency.
- **Auth** is an `X-API-Key` header on every endpoint except `/healthz`.
- **Errors** are enum-coded (`ErrorResponse.error_code`); no stack traces, no
  document content, no file names leak into responses or logs.
- **Remark rule** (D-052): a MATCH surfaces the validation summary; a
  non-MATCH surfaces the match summary.
- **No LLM, no network** in `apmatch/api/`; enforced by
  `tests/api/test_no_llm.py`.

## Container image

The API ships as a self-contained Docker image (`Dockerfile`, multi-stage):

- **Builder stage** installs the Python runtime deps from `requirements.txt`
  into a venv. **Runtime stage** is `python:3.12-slim` with the system libs
  cv2/paddle need (`libgl1`, `libglib2.0-0`, `libgomp1`, `libsm6`, `libxext6`,
  `libxrender1`) plus `curl` for the healthcheck.
- **Models are baked into the image** (`models/` → `/app/models`, owned by the
  app user). The embedding model
  (`/app/models/embeddings/paraphrase-multilingual-MiniLM-L12-v2`, EMB-02) is
  included; see `models/embeddings/MODEL_INFO.md` for provenance and the
  weights hash. Image size ~7.7 GB. Model updates ship as new image versions,
  not out-of-band file drops (D-055).
- **Non-root** user `apmatch`.
- **Offline env vars** are set at build time (`ENV` in the Dockerfile):
  `HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE`,
  `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK` — before any app code imports OCR.
- **Healthcheck** hits `/healthz` (no auth required).
- **`DATABASE_URL` and `APMATCH_API_KEY` are injected at runtime by compose** —
  never baked in. The API key is required at compose start
  (`${APMATCH_API_KEY:?...}`, D-056).
- **Uvicorn runs single-worker** (D-057): startup loads ~1.2 GB of models;
  horizontal scaling is via container replicas, not uvicorn workers.
- **Architecture:** amd64 only (`linux/amd64`). The Paddle stack has no
  `linux/arm64` wheels at the pinned version, so the image cannot be built for
  arm64 (D-059). An arm64 host must build the amd64 image (QEMU emulation) and
  run it. Production tags come from CI.
- **Dev override:** to iterate on model files without rebuilding, mount a
  volume at `/app/models` — it shadows the baked-in copy.
- **Full-stack smoke test** (`scripts/smoke_test.sh`) is the install-and-run
  proof. It runs on **linux/amd64** (real hardware). It is NOT runnable under
  QEMU emulation on Apple Silicon: Paddle's oneDNN backend hits
  `ConvertPirAttribute2RuntimeAttribute not support` under QEMU (D-062).
- **Local Apple Silicon:** the smoke test skips cleanly (even with
  `APMATCH_RUN_SMOKE=1` set), explaining that amd64 is required.
- **CI:** `.github/workflows/ci.yml` includes a `smoke` job that runs on
  `ubuntu-latest`. The workflow is a stub until the repo is pushed and CI is
  enabled (D-063).

## Embedding layer

A local, deterministic text-embedding model is loaded at API
startup and used by the matching layer for semantic similarity
(see EMB-06). The layer is at apmatch/embeddings/.

- Model: paraphrase-multilingual-MiniLM-L12-v2 (~470 MB on disk).
- Weights are vendored in models/embeddings/ and hashed. The
  hash is recorded per-decision in the audit log (D-080).
- The rest of the codebase interacts with embeddings exclusively
  via EmbeddingModel (apmatch/embeddings/model.py).
- Offline: HF_HUB_OFFLINE and TRANSFORMERS_OFFLINE are set at
  module import time, before sentence-transformers is imported.
- Determinism: same input → same vector, byte-identical across
  processes. Locked by tests in tests/embeddings/test_model.py.
- Thresholds are Python constants, not config files
  (apmatch/embeddings/config.py). Accept = 0.70,
  review-band = [0.55, 0.70).

Note: this layer uses a *non-generative encoder*. It cannot
invent text. It maps text to vectors for similarity comparison
only. No LLM in the decision path (see D-046, D-080).

## Linting and dev tooling

- **ruff**, configured via `ruff.toml` at the repo root. `ruff check .` is
  the lint gate; `ruff format` is NOT run as part of linting (formatting is
  a separate, deliberate decision — see D-048).
- Runtime deps in `requirements.txt`; dev-only tools in
  `requirements-dev.txt`, which extends it (`-r requirements.txt`). A fresh
  dev env is `pip install -r requirements-dev.txt`.
- Line length 100, enforced by the formatter, not the linter (E501 ignored).
- The `RUF032` rule (Decimal-from-float) is enabled deliberately: money
  arithmetic must never originate from a float literal. See D-011 and D-048.

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
- Legacy SQLite `ap_automation.db` is not yet migrated; this is P1-10c and
  dev-only.
- The prototype's REAL-typed money columns have been replaced by NUMERIC —
  this is a hard cutover, not a compatible upgrade.
