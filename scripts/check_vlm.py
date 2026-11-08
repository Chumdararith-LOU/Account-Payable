#!/usr/bin/env python3
"""
Smoke-check the VLM extractor on one image before a long batch run.

Prints the model, its digest, which output format the server accepted
(schema = structured outputs, json = older Ollama), the timing, any field
errors, and the extracted document.

Usage:
  python scripts/check_vlm.py [image] [--kind invoice|purchase_order|grni|payment_advice]
  (default image: documents/demo/invoice.png)
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apmatch.parse import vlm
from apmatch.parse.dispatch import DocumentKind


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image", nargs="?", default="documents/demo/invoice.png")
    ap.add_argument("--kind", default="invoice", choices=[k.value for k in DocumentKind])
    args = ap.parse_args()

    print(f"server={vlm.VLM_BASE_URL} model={vlm.VLM_MODEL} prompt={vlm.PROMPT_VERSION}")
    res = vlm.extract_vlm_detailed(DocumentKind(args.kind), Path(args.image))
    summary = res.summary()
    summary.pop("raw_output")
    print(json.dumps(summary, indent=2))
    if res.document is None:
        print("RESULT: FAILED — see error above. Raw output:")
        print((res.raw_output or "")[:2000])
        return 1
    print(json.dumps(dataclasses.asdict(res.document), indent=2, default=str, ensure_ascii=False))
    print("RESULT: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
