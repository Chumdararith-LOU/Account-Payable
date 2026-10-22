# APMatch

Deterministic accounts-payable document matching. Given a vendor **invoice**,
the **purchase order (PO)**, the **goods-received note (GRN)**, and the
**payment advice (PARD)** as images, APMatch OCRs them, extracts the fields,
validates the arithmetic, matches the line items, and routes the result to
**AUTO_APPROVE / HUMAN_REVIEW / REJECT** with a full audit trail.

## Key properties

- **Fully offline at runtime.** No network calls, no external APIs. All model
  weights are vendored locally under `models/` (gitignored) and loaded from
  disk. One-time network use is allowed *only* to download the models (see
  [Model weights](#model-weights)).
- **No generative model in the decision path.** OCR is PaddleOCR
  (PP-OCRv6 + PP-StructureV3); the only learned component in matching is a
  small deterministic sentence-embedding model (MiniLM-L12-v2) used as a
  similarity fallback for line-item descriptions. No LLM anywhere.
- **Deterministic.** Pinned weights, greedy decoding, fixed seeds. The same
  inputs produce the same decision.
- **Money is `decimal.Decimal`** end to end. Never `float`.

## Requirements

- **Python 3.12** (the project pins 3.12; do not use a system 3.9/3.10).
- **conda** (recommended) or any virtualenv.
- **~2 GB free disk** for model weights.
- **~5 GB RAM** to run the OCR + embedding stack (CPU-only; no GPU needed).
  The API container uses ~4.5 GB once warm.
- **Docker + Docker Compose** (optional, for the Postgres-backed API).

Cross-platform: the setup below works on **Windows, Linux, and macOS**. The
only platform-specific note is the conda activation command (see
[Setup](#setup)).

## Setup

### 1. Clone

```bash
git clone https://github.com/Chumdararith-LOU/Account-Payable.git
cd Account-Payable
```

### 2. Create the environment

```bash
conda create -n anpr python=3.12 -y
# activate (use the form for your shell):
conda activate anpr          # bash / zsh / Linux / macOS
anpr\Scripts\activate        # Windows cmd
anpr\Scripts\Activate.ps1    # Windows PowerShell
```

### 3. Install dependencies

`torch` must resolve to the **CPU build** (the standard PyPI wheels bundle
CUDA). The `constraints.txt` + `--extra-index-url` pair pins it:

```bash
# Linux / macOS
pip install -r requirements.txt -c constraints.txt \
  --extra-index-url https://download.pytorch.org/whl/cpu

# Windows (CPU wheels live on the main index; the cpu index has no win builds)
pip install -r requirements.txt
```

Dev tools (ruff): `pip install -r requirements-dev.txt`.

### 4. Download the model weights

```bash
python scripts/download_models.py
```

This is the **only** step that needs the network. It fetches ~1.7 GB into
`models/` (see [Model weights](#model-weights) for what it downloads and how
to verify it). Re-running is safe — already-present models are skipped.

### 5. Configure the environment

```bash
cp .env.example .env
# edit .env: set APMATCH_API_KEY to a random value, e.g.
#   python -c "import secrets; print(secrets.token_hex(32))"
```

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

To call the match endpoint:

```bash
curl -X POST http://localhost:8000/match \
  -H "X-API-Key: $APMATCH_API_KEY" \
  -F "invoice=@documents/invoice/INV_2026_1123.png" \
  -F "po=@documents/po/PO_2026_0451.png" \
  -F "grni=@documents/grni/GRN_2026_0322.png" \
  -F "pard=@documents/pard/PARD_2026_0210.png"
```

### Running without Docker

If you prefer to run the API in-process (e.g. to debug), start Postgres
first (`docker compose up postgres -d`), apply the migrations
(`alembic upgrade head`), then:

```bash
uvicorn apmatch.api.app:app --host 0.0.0.0 --port 8000
```

## Running the tests

```bash
pytest            # full suite
pytest tests/integration/   # end-to-end pipeline tests (slow — they run real OCR)
```

The integration tests run the real OCR pipeline, so they are slow by design
(roughly 40 minutes for the embedding demo module on a CPU-only machine).
The unit tests (matching, validation, parsing, scoring) are fast.

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
  audit/            append-only audit log (SHA-256 input hashing)
  store/            SQLAlchemy ORM models
  api/              FastAPI service (pipeline, app, schemas, config)
tests/              pytest suite (unit + integration + smoke)
scripts/            dev tools (download_models, offline verify, deploy, ...)
models/             vendored model weights (gitignored)
documents/          test fixtures (real + generated demo set)
alembic/            database migrations
docs/               ARCHITECTURE, DECISIONS, TASKS, DEPLOYMENT, ...
```

## Docs

- `docs/ARCHITECTURE.md` — module-by-module map and the document contract.
- `docs/DECISIONS.md` — the decision log (every threshold and trade-off).
- `docs/DEPLOYMENT.md` — remote deployment parameters and runbook.
- `docs/OFFLINE_MODELS.md` — how the offline model caches were discovered.
- `docs/DEV_WORKFLOW.md` — the Mac-edit / server-run development workflow.
- `AGENTS.md` — operating rules for agents working in this repo.
