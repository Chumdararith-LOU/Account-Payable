# OFFLINE_MODELS.md — model weight cache discovery (P1-02, Sub B)

Factual snapshot taken 2026-09-26 after the first PaddleOCR 3.7.0
instantiation in the `anpr` env. No vendoring done yet — that is P1-03/04.

## Discovered caches

| Model | Source | Local cache path found | Size | Currently present |
|---|---|---|---|---|
| PP-OCRv6_medium_det | Paddle (via PaddleX official-model fetch) | `~/.paddlex/official_models/PP-OCRv6_medium_det` | 59 MB | yes |
| PP-OCRv6_medium_rec | Paddle (via PaddleX official-model fetch) | `~/.paddlex/official_models/PP-OCRv6_medium_rec` | 86 MB | yes |
| PP-LCNet_x1_0_doc_ori (doc orientation) | Paddle (via PaddleX) | `~/.paddlex/official_models/PP-LCNet_x1_0_doc_ori` | 6.6 MB | yes |
| UVDoc (doc unwarping) | Paddle (via PaddleX) | `~/.paddlex/official_models/UVDoc` | 31 MB | yes |
| (legacy 2.x det/rec/cls wheels) | Paddle (old paddleocr 2.9.1) | `~/.paddleocr/whl/{det,rec,cls}` | 16 MB total | yes (stale, from 2.x era) |
| TrorYongOCR (Khmer candidate) | Hugging Face (`KrorngAI/TrorYongOCR`) | `~/.cache/huggingface/hub/` — **not present** (no download triggered) | — | no |

Notes:

- `~/.paddlex/official_models/` totals **184 MB**. This is the primary
  Paddle weight store for PaddleOCR 3.x.
- PaddleX also writes 4 KB metadata stubs under
  `~/.cache/huggingface/hub/models--PaddlePaddle--*` (created at download
  time); the actual weight bytes are in `~/.paddlex/official_models/`.
- The HF hub cache root `~/.cache/huggingface/hub/` exists (979 MB total,
  mostly unrelated models from other projects). TrorYongOCR weights are NOT
  in it yet; P1-04 must pre-download `KrorngAI/TrorYongOCR` once (network
  allowed at setup time) and then run fully offline.
- First-run log also showed PaddleX performing a "connectivity to the model
  hosters" check; the log line itself names the bypass:
  `set PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK to True`.

## Plan for P1-03 / P1-04

P1-03/P1-04 will copy the weights above into `models/` inside the repo
(gitignored) and point the runtime at them, with offline env vars set so the
pipeline never reaches the network at runtime. One-time network use is
allowed at setup/vendor time only.

## Candidate offline env vars to test in P1-03

- `HF_HUB_OFFLINE=1`
- `TRANSFORMERS_OFFLINE=1`
- `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True` (candidate; verify — name
  taken verbatim from the PaddleX log message in A.4)

`models/` is intentionally NOT in `.gitignore` yet; it gets added when the
directory is actually created in P1-03.
