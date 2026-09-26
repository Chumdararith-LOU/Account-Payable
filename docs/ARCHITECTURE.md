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
| `remark_generator.py` | Optional Claude (Haiku 4.5) one-line remark generator with raw-text fallback; not wired into the engine |
| `generate_test_docs.py` | Generates bilingual EN/Khmer test docs (PO/GRNI/INV/PARD) as PDF+PNG via WeasyPrint + pdftoppm |

Supporting: `migrate_to_db.py` (one-shot JSON→SQLite), `generate_report.py`
(static HTML completion report), `set_api_key_visible.py` (writes `.env`),
`Plan.md` (proposal), `report.md` (P1-00 recon).

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
- No OCR invocation code exists in the repo; the OCR JSONs in `output/ocr/`
  were produced externally.
- `cloudflared-linux-amd64` is a Linux binary, unusable on this macOS host.
- `tror-yong-ocr` is installed in `anpr` but unaudited (audit performed in
  P1-01 step 11; see report).
