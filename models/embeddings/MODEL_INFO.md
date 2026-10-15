# Embedding model: paraphrase-multilingual-MiniLM-L12-v2

## Provenance
- Source: https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
- License: Apache 2.0
- Downloaded: 2026-10-13
- Size on disk: ~488 MB (PyTorch weights + tokenizer; the repo's redundant
  onnx/openvino/tf/pytorch weight formats were not vendored)

## Weights hash (SHA-256)
- model.safetensors: `eaa086f0ffee582aeb45b36e34cdd1fe2d6de2bef61f8a559a1bbc9bd955917b`

## Why this model
- Multilingual (50+ languages including Khmer), necessary for
  bilingual invoices.
- Small enough to fit alongside PaddleOCR + PP-StructureV3 on
  a resource-constrained server (~500 MB resident).
- Deterministic when run with pinned weights and offline env
  vars (see apmatch/embeddings/model.py, EMB-03).
- Fully local; no external API calls.

## Offline loading
Loaded via sentence-transformers with:
  HF_HUB_OFFLINE=1
  TRANSFORMERS_OFFLINE=1
and an explicit model path pointing at this directory. See
apmatch/embeddings/ for the wrapper (EMB-03).

## Provenance verification
To verify the vendored copy matches upstream:
  shasum -a 256 model.safetensors
and compare to the value above.

If this file changes, the audit log will contain the old hash
and new decisions will contain the new hash — the model version
is thus traceable per-decision (see D-080).
