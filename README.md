# APMatch

Deterministic, offline accounts-payable document matching for BPO operations — every invoice decision is rule-based, auditable, and isolated per customer.

## What this is

APMatch is the document-processing core of a BPO (business process outsourcer)
that processes AP documents on behalf of SME clients. Given a vendor
**invoice**, the **purchase order (PO)**, the **goods-received note (GRN)**,
and the **payment advice (PARD)** as images, APMatch OCRs them, extracts the
fields, validates the arithmetic, matches the line items, and routes the
result to **AUTO_APPROVE / HUMAN_REVIEW / REJECT** — fully offline, fully
deterministic, with a tamper-evident audit trail. Every run is tagged with a
`customer_id`, so one client's documents never mix with another's.

## Business model

APMatch is operated by a BPO (business process outsourcer) that
processes AP documents on behalf of SME clients. Documents are
priced per document; there is no subscription. Each document is
isolated by `customer_id` and every decision is recorded in a
tamper-evident audit log. The pipeline runs fully offline on
the operator's own hardware — no cloud API calls, no per-document
fees, no data leaves the machine.

The deterministic design is what makes the business model work:
customers ask "why did you reject this invoice?" and the operator
can show them the exact rule that fired, the exact OCR text that
was read, the exact similarity score if embeddings were involved,
and a SHA-256 hash of the input documents to prove nothing was
altered.

## Status

- **Phase 1: complete.** Full pipeline (OCR → parse → validate → match →
  score → route → audit), FastAPI + Postgres, deployment runbook, and the
  embedding-based line-item fallback.
- **BPO production work: ongoing.** GPU acceleration (PROD-A1), batch
  endpoint (PROD-A2), customer-scoped templates (PROD-B).

## Quick start (5 minutes)

Requirements: **Python 3.12** (via conda or any virtualenv), **~2 GB disk**
for model weights, **~5 GB RAM** (CPU-only; no GPU needed), and Docker +
Compose for the Postgres-backed API. Works on **Windows, Linux, and macOS**.

```bash
# 1. Clone
git clone https://github.com/Chumdararith-LOU/Account-Payable.git
cd Account-Payable

# 2. Environment
conda create -n anpr python=3.12 -y
conda activate anpr          # Windows: anpr\Scripts\activate

# 3. Dependencies (CPU torch on Linux/macOS; plain install on Windows)
pip install -r requirements.txt -c constraints.txt \
  --extra-index-url https://download.pytorch.org/whl/cpu   # Linux/macOS
pip install -r requirements.txt                             # Windows

# 4. Model weights (the only step that needs the network)
python scripts/download_models.py

# 5. Configure
cp .env.example .env
# edit .env: set APMATCH_API_KEY to a random value, e.g.
#   python -c "import secrets; print(secrets.token_hex(32))"

# 6. Run
docker compose up --build
# API on http://localhost:8000  (health: /healthz)
```

Dev tools (ruff): `pip install -r requirements-dev.txt`.

## How it works

```
 invoice.png   po.png   grn.png   pard.png
     │           │         │         │
     └───────────┴─────────┴─────────┘
                    │
             ┌──────▼──────┐
             │     OCR      │  PP-OCRv6 text + PP-StructureV3 tables
             └──────┬──────┘  (Khmer script routed to TrorYongOCR)
             ┌──────▼──────┐
             │    Parse     │  spatial label→value extraction → frozen dataclasses
             └──────┬──────┘  (Decimal money, typed dates, document numbers)
             ┌──────▼──────┐
             │   Validate   │  arithmetic consistency: subtotal / tax / total
             └──────┬──────┘
             ┌──────▼──────┐
             │    Match     │  4-way line-item match: PO / GRN / Invoice / PARD
             └──────┬──────┘  (exact first; embedding similarity as fallback)
             ┌──────▼──────┐
             │    Score     │  confidence score → AUTO_APPROVE / HUMAN_REVIEW / REJECT
             └──────┬──────┘
             ┌──────▼──────┐
             │    Audit     │  append-only row: decision, failures, SHA-256 input
             └─────────────┘  hash, customer_id
```

## Design principles

| Principle | What it means |
|---|---|
| **Fully offline at runtime** | No network calls, no external APIs. All model weights are vendored locally under `models/` (gitignored) and loaded from disk. One-time network use is allowed *only* to download the models. |
| **No generative model in the decision path** | OCR is PaddleOCR (PP-OCRv6 + PP-StructureV3); the only learned component in matching is a small deterministic sentence-embedding model (MiniLM-L12-v2) used as a similarity fallback for line-item descriptions. No LLM anywhere. |
| **Deterministic** | Pinned weights, greedy decoding, fixed seeds. The same inputs produce the same decision. |
| **Money is `decimal.Decimal`** | End to end. Never `float`. |
| **Auditable** | Every run writes one append-only audit row: the decision, every failed check with expected/actual/delta, and a SHA-256 hash of the input documents. No update, no delete. |
| **Customer isolation** | Every `/match` request carries a `customer_id`; every audit row stores it; every KPI query can filter by it. Two clients processed concurrently never mix. |

## Model weights

`models/` is gitignored (weights are too large for git). The runtime loads
from three subdirectories; `scripts/download_models.py` populates all three:

| Directory | What | Source | Size |
|---|---|---|---|
| `models/paddleocr/` | 14 PaddleOCR / PP-StructureV3 models (OCR + table structure) | PaddleX official models | ~1.2 GB |
| `models/khmer/` | TrorYongOCR (Khmer-script OCR) | Hugging Face `KrorngAI/TrorYongOCR` | ~21 MB |
| `models/embeddings/paraphrase-multilingual-MiniLM-L12-v2/` | sentence-embedding model | Hugging Face `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | ~476 MB |

The download script uses `paddlex` (for the Paddle models) and
`huggingface_hub` (for the two Hugging Face models), both already in
`requirements.txt`. It works identically on Windows, Linux, and macOS.

**Verify the embedding weights** (the runtime re-checks this hash on every
load and refuses to start on a mismatch — see
`models/embeddings/MODEL_INFO.md`):

```bash
# Linux / macOS
shasum -a 256 models/embeddings/paraphrase-multilingual-MiniLM-L12-v2/model.safetensors
# Windows (PowerShell)
Get-FileHash -Algorithm SHA256 models\embeddings\paraphrase-multilingual-MiniLM-L12-v2\model.safetensors
```

Expected SHA-256:
`eaa086f0ffee582aeb45b36e34cdd1fe2d6de2bef61f8a559a1bbc9bd955917b`

If a download is interrupted, just re-run `python scripts/download_models.py`
— it skips what is already present and fetches the rest.

## Running the API

The API is a FastAPI service backed by Postgres. The simplest way to run it
is Docker Compose (starts Postgres + the API):

```bash
docker compose up --build
# API on http://localhost:8000  (health: /healthz)
```

`APMATCH_API_KEY` must be set (from `.env` or the environment) — a container
with no API key refuses to start.

To call the match endpoint (optionally tagged with a `customer_id`):

```bash
curl -X POST "http://localhost:8000/match?customer_id=hotel_demo" \
  -H "X-API-Key: $APMATCH_API_KEY" \
  -F "invoice=@documents/invoice/INV_2026_1123.png" \
  -F "po=@documents/po/PO_2026_0451.png" \
  -F "grni=@documents/grni/GRN_2026_0322.png" \
  -F "pard=@documents/pard/PARD_2026_0210.png"
```

`customer_id` is optional (default `"default"`); it must match
`^[a-z0-9_-]{1,64}$` or the request is rejected with 400
`INVALID_CUSTOMER_ID`.

### Running without Docker

If you prefer to run the API in-process (e.g. to debug), start Postgres
first (`docker compose up postgres -d`), apply the migrations
(`alembic upgrade head`), then:

```bash
uvicorn apmatch.api.app:app --host 0.0.0.0 --port 8000
```

## Running the demo

Demo case runner: coming in EMB-12.

## Testing

```bash
pytest            # full suite
pytest tests/integration/   # end-to-end pipeline tests (slow — they run real OCR)
```

The integration tests run the real OCR pipeline, so they are slow by design
(tens of minutes on a CPU-only machine). The unit tests (matching,
validation, parsing, scoring) are fast.

Lint: `ruff check .` (config in `ruff.toml`).

## Project layout

```
apmatch/            the production package
  ocr/              OCR engines (Latin PaddleOCR + Khmer TrorYongOCR) + router
  layout/           PP-StructureV3 table extraction
  parse/            OCR -> dataclass field extraction (spatial + regex)
  schema/           frozen document dataclasses + Decimal coercion
  validation/       arithmetic-consistency checks
  matching/         4-way match engine (PO / GRN / Invoice / PARD)
  embeddings/       deterministic sentence-embedding wrapper (offline)
  scoring/          confidence score + 3-valued routing
  remarks/          deterministic match remarks
  audit/            append-only audit log (SHA-256 input hashing, customer_id)
  store/            SQLAlchemy ORM models
  api/              FastAPI service (pipeline, app, schemas, config)
tests/              pytest suite (unit + integration + smoke)
scripts/            dev tools (download_models, offline verify, deploy, ...)
models/             vendored model weights (gitignored)
documents/          test fixtures (real + generated demo set)
alembic/            database migrations
docs/               ARCHITECTURE, DECISIONS, TASKS, DEPLOYMENT, ...
```

## Development workflow

Local editing, remote execution:

- Edit code on the dev machine; run the fast tests locally
  (`pytest tests/ --ignore=tests/integration`).
- Run the full suite (including OCR) on the server:
  `./scripts/remote_pytest.sh tests/ -v` (syncs the tree, runs pytest in a
  one-off container against the `apmatch_test` database — never the
  production DB).
- Deploy: `./scripts/deploy_remote.sh <ssh-target>` (rsync + build +
  healthz check). See `docs/DEPLOYMENT.md` for the locked-in parameters and
  `docs/DEV_WORKFLOW.md` for the full workflow.

## Environment variables

| Variable | Required | Default | Meaning |
|---|---|---|---|
| `APMATCH_API_KEY` | yes | — | API key for `X-API-Key` auth (≥ 16 chars; no default by design) |
| `DATABASE_URL` | yes | — | Postgres connection string (compose sets it) |
| `APMATCH_LOG_LEVEL` | no | `INFO` | logging level |
| `APMATCH_OCR_DEBUG` | no | `false` | log OCR block/table counts per document |
| `APMATCH_MAX_UPLOAD_BYTES` | no | `20971520` (20 MB) | per-file upload limit |

## Troubleshooting

- **`APMATCH_API_KEY is required and has no default`** — create `.env` from
  `.env.example` and set the key (step 5 of the quick start).
- **Embedding hash mismatch at startup** — the weights in
  `models/embeddings/` don't match the pinned hash; re-run
  `python scripts/download_models.py`.
- **Port 8000 already in use** — change the published port in
  `docker-compose.yml`.
- **First `/match` is slow** — the OCR engines warm up on first use
  (tens of seconds); subsequent requests are faster.
- **Windows + CUDA torch** — if `torch` resolved to a CUDA build, reinstall
  with the plain `pip install -r requirements.txt` (Windows CPU wheels live
  on the main index).

## Embeddings

Line-item descriptions that don't match exactly (reworded, translated, or
OCR-garbled) fall back to a deterministic sentence-embedding similarity
check (MiniLM-L12-v2, multilingual). The score lands in one of two bands:
`[0.55, 0.70)` = match but route to human review (a WARNING is recorded);
`>= 0.70` = auto-match. Every similarity match is stored on the audit row
with its score, thresholds, and model version, so the evidence is
reproducible. The model runs offline from the vendored weights and is
hash-verified on every load.

## Docs

- `docs/ARCHITECTURE.md` — module-by-module map and the document contract.
- `docs/DECISIONS.md` — the decision log (every threshold and trade-off).
- `docs/DEPLOYMENT.md` — remote deployment parameters and runbook.
- `docs/OFFLINE_MODELS.md` — how the offline model caches were discovered.
- `docs/DEV_WORKFLOW.md` — the local-edit / server-run development workflow.
- `AGENTS.md` — operating rules for agents working in this repo.

## Contributing

- Read `AGENTS.md` first — the hard rules (no generative model in the
  decision path, no runtime network, `decimal.Decimal` for money, tests for
  every new module) are non-negotiable.
- One commit per task; task tracking lives in `docs/TASKS.md`.
- Run `ruff check .` and the fast test suite before committing.

## Contact

- **Owner:** Lou Chandaerith
- **Repo:** https://github.com/Chumdararith-LOU/Account-Payable
- **Team:** Kong Vong · Lou Chandaerith · Thai Taiwan · Pholl Chanphayuk ·
  Bun Sengleang · Loy Lyher

## License

MIT License (matching the runtime dependencies: PaddleOCR is Apache 2.0,
MiniLM is Apache 2.0, sentence-transformers is Apache 2.0). See LICENSE.
