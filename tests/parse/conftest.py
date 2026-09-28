"""Shared helpers for the extraction-layer tests."""

import json

from apmatch.ocr.engine import OCRResult, Table, TextBlock
from tests.conftest import REPO_ROOT

OCR_DIR = REPO_ROOT / "output" / "ocr"


def _load_ocr_result(path: str) -> OCRResult:
    """Load an output/ocr/*.json fixture into an OCRResult."""
    data = json.loads((OCR_DIR / path).read_text(encoding="utf-8"))
    return OCRResult(
        source_file=data.get("source_file", ""),
        text_blocks=tuple(
            TextBlock(text=b["text"], bbox=tuple(b["bbox"]))
            for b in data.get("text_blocks", [])
        ),
        tables=tuple(
            Table(html=t["html"], bbox=tuple(t["bbox"]) if t.get("bbox") else (0, 0, 0, 0))
            for t in data.get("tables", [])
        ),
    )
