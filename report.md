# TASK P1-00 — Repo Baseline & Dependency Audit

Date: 2026-09-26 · Mode: read-only reconnaissance (no installs, no commits)

---

## 1. Raw command output

### 1.1 Python & package indexes

```
$ python3 --version            # system python
Python 3.9.6

$ which python3
/usr/bin/python3
```

`pip index versions` (run with the `anpr` conda env's pip, Python 3.12.13):

```
$ pip index versions paddleocr
paddleocr (3.7.0)
Available versions: 3.7.0, 3.6.0, 3.5.0, 3.4.1, 3.4.0, 3.3.3, 3.3.2, 3.3.1, 3.3.0,
3.2.0, 3.1.1, 3.1.0, 3.0.3, 3.0.2, 3.0.1, 3.0.0, 2.10.0, 2.9.1, 2.9.0, 2.8.1, 2.8.0,
2.7.3, 2.7.2, 2.7.0.3, 2.7.0.2, 2.7.0.1, 2.7.0.0, 2.6.1.3, 2.6.1.2, 2.6.1.1, 2.6.1.0,
2.6.0.3, 2.6.0.2, 2.6.0.1, 2.6, 2.5.0.3, 2.5.0.2, 2.5, 2.4.0.4, 2.4.0.3, 2.4.0.2,
2.4.0.1, 2.4, 2.3.0.2, 2.3.0.1, 2.3, 2.2.0.2, 2.2.0.1, 2.2, 2.0.6, 2.0.5, 2.0.4,
2.0.3, 2.0.2, 2.0.1, 1.1.1, 1.0.1, 1.0.0, 0.0.3.1, 0.0.3, 0.0.2, 0.0.1.1, 0.0.1.0
  INSTALLED: 2.9.1
  LATEST:    3.7.0

$ pip index versions paddlepaddle
paddlepaddle (3.3.1)
Available versions: 3.3.1, 3.3.0, 3.2.2, 3.2.1, 3.2.0, 3.1.1, 3.1.0, 3.0.0, 2.6.2
  INSTALLED: 2.6.2
  LATEST:    3.3.1

$ pip index versions pytesseract
pytesseract (0.3.13)
Available versions: 0.3.13, 0.3.10, 0.3.9, 0.3.8, 0.3.7, 0.3.6, 0.3.5, 0.3.4, 0.3.3,
0.3.2, 0.3.1, 0.3.0, 0.2.9, 0.2.8, 0.2.7, 0.2.6, 0.2.5, 0.2.4, 0.2.2, 0.2.0,
0.1.9, 0.1.8, 0.1.7, 0.1.6, 0.1.5, 0.1.4, 0.1.3, 0.1
  (not installed in any env)

$ tesseract --list-langs
zsh: command not found: tesseract   # tesseract binary NOT installed on this machine
```

### 1.2 Repo state

```
$ git status
fatal: not a git repository (or any of the parent directories): .git

$ git log --oneline -20
fatal: not a git repository (or any of the parent directories): .git
```

**The project is NOT a git repository.** No version control exists yet.

```
$ find . -maxdepth 3 -type f -name '*.py'
./ai_engine.py
./set_api_key_visible.py
./pp.py
./database.py
./remark_generator.py
./dashboard.py
./api.py
./generate_test_docs.py
./migrate_to_db.py
./generate_report.py
./.venv/bin/vba_extract.py
```

### 1.3 Environments

```
$ conda env list
# conda environments:
#
# * -> active
# + -> frozen
base                     /opt/homebrew/Caskroom/miniconda/base
anpr                     /opt/homebrew/Caskroom/miniconda/base/envs/anpr
bootcamp                 /opt/homebrew/Caskroom/miniconda/base/envs/bootcamp
car_defect               /opt/homebrew/Caskroom/miniconda/base/envs/car_defect
deepseek                 /opt/homebrew/Caskroom/miniconda/base/envs/deepseek
deepseek-x86             /opt/homebrew/Caskroom/miniconda/base/envs/deepseek-x86
mindspore                /opt/homebrew/Caskroom/miniconda/base/envs/mindspore
movie-rec                /opt/homebrew/Caskroom/miniconda/base/envs/movie-rec
myenv                    /opt/homebrew/Caskroom/miniconda/base/envs/myenv

$ ls -d ~/.virtualenvs/* .venv venv
.venv                      # exists in project dir — but BROKEN (see §2.4)
(no ~/.virtualenvs, no venv/)
```

Per-env Python versions:

| env | Python | paddleocr | paddlepaddle | fastapi/uvicorn | streamlit/plotly | bs4 |
|---|---|---|---|---|---|---|
| anpr | 3.12.13 | **2.9.1** | **2.6.2** | — | — | 4.15.0 |
| bootcamp | 3.11.15 | — | — | — | — | 4.14.3 |
| car_defect | 3.10.20 | — | — | 0.139.0 / 0.51.0 | — | 4.15.0 |
| deepseek | 3.12.13 | — | — | 0.141.1 / 0.52.1 | — | — |
| deepseek-x86 | 3.12.11 | — | — | 0.136.1 / 0.46.0 | — | — |
| mindspore | 3.9.23 | — | — | — | — | — |
| movie-rec | 3.11.16 | — | — | — | — | 4.14.3 |
| myenv | 3.10.19 | — | — | 0.139.0 / 0.50.2 | 1.59.1 / 6.5.2 | 4.14.3 |

`anpr` also has: opencv (4.10/4.11), torch 2.5.1, torchvision, ultralytics 8.3.40,
pandas 3.0.5, numpy 1.26.4, transformers 4.47.1, python-docx, scikit-learn,
matplotlib, `tror-yong-ocr 0.2.7` (a Khmer OCR package — relevant to the Khmer-script
requirement in Plan.md §5).

---

## 2. Repository detail

### 2.1 What the project is

**DPAI — AI-Powered AP Invoice Matching** (Turing Hackathon Cycle 11).
Automates 4-way AP reconciliation: Purchase Order (PO), Goods Received Note (GRNI),
Vendor Invoice, Payment Advice (PARD). Deterministic rule engine + classical OCR;
no generative model in the decision path. See `Plan.md` for the full proposal.

Pipeline: document image → OCR (PaddleOCR PP-Structure, run externally) → JSON
(`text_blocks` + `tables`) → field extraction (regex + spatial bbox heuristics) →
SQLite → 3/4-way matching engine → MATCH / DISCREPANCY / PENDING INFO → dashboard.

### 2.2 File inventory (root)

| File | Purpose |
|---|---|
| `Plan.md` | Project proposal: architecture, roadmap (Phase 1 = PP-OCRv6 + PP-StructureV3 + Khmer module + PostgreSQL), GTM/pricing, risks |
| `database.py` (459 ln) | SQLite layer: schema (8 tables), insert fns, JSON→field extractors (`extract_{po,grni,invoice,pard}_from_json`), spatial OCR helper `get_text_below_label`, migration, dashboard stats |
| `ai_engine.py` (127 ln) | Matching engine: vendor lookup, line-item join via `normalize_text` (strips OCR noise like `/nmw`), qty/price/payment rules, score 0–1, writes MATCH_RESULT |
| `pp.py` (126 ln) | Document-processing dispatcher: routes doc_type → insert fn, invoice duplicate check, `save_match_result` (queue routing commented out) |
| `api.py` (186 ln) | FastAPI service v1.1: `/health`, `/samples`, `/stats`, `/process`, `/process-direct`, `/process-file` (API-key auth, hardcoded demo key `DPAI-DEMO-2026`), embedded demo HTML page |
| `dashboard.py` (274 ln) | Streamlit KPI dashboard: metric cards, top-discrepancy bar chart (Plotly), processing log table |
| `remark_generator.py` (107 ln) | Optional Claude (Haiku 4.5) one-line remark generator with raw-text fallback; **not yet wired into ai_engine.py** |
| `generate_test_docs.py` (248 ln) | Generates bilingual EN/Khmer test docs (PO/GRNI/INV/PARD) as PDF+PNG via WeasyPrint + pdftoppm |
| `migrate_to_db.py` (19 ln) | One-shot `output/ocr/*.json` → SQLite migration |
| `generate_report.py` (160 ln) | Emits `AP_AI_Automation_Report.html` (static completion report) |
| `set_api_key_visible.py` (25 ln) | Writes `ANTHROPIC_API_KEY` to `.env` |
| `.env` | Contains `ANTHROPIC_API_KEY` (value redacted here) |
| `ap_automation.db` | SQLite DB, 69 KB |
| `cloudflared-linux-amd64` (40 MB) | Tunnel binary (Linux — not usable on this macOS host) |
| `tunnel.log` (7.3 MB), `uvicorn.log` | Runtime logs |
| `invoice_output.json`, `payload_inv.json`, `curl_result.txt` | Sample payloads / test artifacts |
| `dashboard.html`, `AP_AI_Automation_Report.html` | Static HTML outputs |
| `opencode.json` | opencode config |

### 2.3 Data directories

- `documents/{po,grni,invoice,pard}/` — source PNGs (test docs; `documents/invoice/` also has `invoice.png`, `Pasted image.png`)
- `test_docs/` — generated PDF+PNG pairs (PO_2026_0451, GRN_2026_0322, INV_2026_1123, PARD_2026_0210)
- `output/ocr/` — OCR JSON results (5 files). Format: `{"source_file", "tables": [{"html"}], "text_blocks": [{"text", "bbox": [x0,y0,x1,y1]}]}`. OCR noise visible in output (e.g. `KINGDOMOFCAMBODIA`, `Description /uww`, `Office Chair/nHnw`)
- `output/` — per-doc `.md` + `_res.json` (PP-Structure markdown + raw results), `output/imgs/` — cropped table/image boxes
- `erp_queue/` — 2 JSONs (matched invoices ready for ERP)
- `pending_queue/`, `review_queue/` — empty
- `__pycache__/` — stale bytecode

### 2.4 Database state (`ap_automation.db`)

| Table | Rows |
|---|---|
| PO_HEADER / PO_LINE | 1 / 6 |
| GRNI_HEADER / GRNI_LINE | 1 / 3 |
| INVOICE_HEADER / INVOICE_LINE | 1 / 3 |
| PARD | 1 |
| MATCH_RESULT | 3 |

One validated test case: Mekong Supplies Co., Ltd., PO-2026-0451 / GRN-2026-0322 /
INV-2026-1123 / PARD-2026-0210, total $1,100.00 → MATCH, score 1.0.

### 2.5 Broken project `.venv`

`.venv/pyvenv.cfg` shows it was created on **another machine**:
`command = /usr/bin/python3 -m venv /home/admin-ubuntu/Downloads/dpai/.venv`
(ubuntu path, Python 3.13.3, `home = /usr/bin`). All shebangs point to a
non-existent interpreter → `.venv/bin/pip` fails with "bad interpreter".
**This venv is unusable on this Mac and should be deleted and rebuilt.**

### 2.6 Code observations (relevant to Phase 1)

- No OCR invocation code exists in the repo — OCR JSONs in `output/ocr/` were produced externally. Phase 1's PP-OCRv6 upgrade means *adding* the OCR stage, not editing existing calls.
- `remark_generator.py` exists but is not imported anywhere (ai_engine.py builds remarks inline).
- `PRICE_TOLERANCE = 0.01` in ai_engine.py is commented "1%" but the proposal says ±5% — comment/code drift.
- API key hardcoded in `api.py` (`DPAI-DEMO-2026`); `.env` key is written but never loaded by any module (no python-dotenv usage).
- No `requirements.txt` / `pyproject.toml` anywhere — dependencies are undeclared.
- `generate_test_docs.py` needs WeasyPrint + `pdftoppm` (poppler) — neither confirmed installed in any env.

---

## 3. Recommendations

### 3.1 Environment: use `anpr`

**Use the `anpr` conda env** (`/opt/homebrew/Caskroom/miniconda/base/envs/anpr`,
Python 3.12.13). It is the only env with the Paddle stack (paddleocr 2.9.1,
paddlepaddle 2.6.2, opencv, plus `tror-yong-ocr` for Khmer). `myenv` has the
web stack (fastapi/uvicorn/streamlit/plotly) but no Paddle.

Plan: consolidate into `anpr` — upgrade the Paddle stack and add the missing
web deps there, so one env runs the whole pipeline:

```
conda activate anpr
pip install -U "paddlepaddle==3.3.1" "paddleocr==3.7.0"
pip install fastapi uvicorn streamlit plotly weasyprint anthropic python-dotenv
```

(WeasyPrint also needs system libs: `brew install pango poppler` for pdftoppm.)

Do NOT use: system `/usr/bin/python3` (3.9.6, too old for paddle 3.x), the
broken project `.venv` (delete it), or `myenv` (would need the full Paddle
stack reinstalled — hundreds of MB).

### 3.2 Does "PP-OCRv6" exist as an installable package?

**No — not as a standalone PyPI package.** `pp-ocrv6` does not exist on PyPI
(404). PP-OCRv6 is a **model family** (tiny 1.5M / small 7.7M / medium 34.5M
params, 50 languages) released **2026-06-11 in PaddleOCR v3.7.0**. You get it by:

```
pip install "paddleocr>=3.7.0"     # latest is exactly 3.7.0
```

Model weights auto-download from Hugging Face (`PaddlePaddle` org) on first run;
`PP-OCRv6_medium` is the default. It also runs via `transformers>=5.8.0`
(`TextRecognition(model_name="PP-OCRv6_medium_rec", engine="transformers")`).

**Caveat:** the installed `anpr` env has paddleocr **2.9.1** (old 2.x API) and
paddlepaddle **2.6.2**. PP-OCRv6 requires the **3.x line** — the upgrade to
paddleocr 3.7.0 + paddlepaddle 3.3.1 is mandatory and is a breaking API change
(`PaddleOCR(...)` 3.x interface vs 2.x). Since no OCR code exists in the repo
yet, the upgrade breaks nothing today.

Note for Plan.md §5: PP-OCRv6's 50-language unified model covers 46 Latin-script
languages — **Khmer is not among them**, confirming the plan's separate
Khmer-model requirement (candidate already present in `anpr`: `tror-yong-ocr`).

### 3.3 Other baseline notes

- **No git repo** — `git init` should be the first write task (with a `.gitignore`
  for `.venv/`, `__pycache__/`, `*.db`, `.env`, `tunnel.log`, `cloudflared-linux-amd64`).
- **tesseract not installed** — pytesseract is moot unless `brew install tesseract`
  is wanted as a second OCR engine (Plan.md mentions a Tesseract Khmer pack option).
- No dependency manifest exists — a `requirements.txt` (or `environment.yml`)
  should be created from the `anpr` env once Phase 1 deps are settled.
