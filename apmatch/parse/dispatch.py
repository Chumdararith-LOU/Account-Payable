"""Dispatcher: document kind + OCRResult -> P1-06 dataclass.

Also holds the shared JSON <-> OCRResult helpers used by the extractor CLIs
and the test suite.
"""

from __future__ import annotations

import dataclasses
import json
from enum import Enum

from apmatch.ocr.engine import OCRResult, Table, TextBlock
from apmatch.parse.grni import extract_grni
from apmatch.parse.invoice import extract_invoice
from apmatch.parse.payment_advice import extract_payment_advice
from apmatch.parse.purchase_order import extract_purchase_order


class DocumentKind(str, Enum):
    INVOICE = "invoice"
    PURCHASE_ORDER = "purchase_order"
    GRNI = "grni"
    PAYMENT_ADVICE = "payment_advice"


_EXTRACTORS = {
    DocumentKind.INVOICE: extract_invoice,
    DocumentKind.PURCHASE_ORDER: extract_purchase_order,
    DocumentKind.GRNI: extract_grni,
    DocumentKind.PAYMENT_ADVICE: extract_payment_advice,
}


def extract(kind: DocumentKind, ocr: OCRResult) -> object:
    """Dispatch to the extractor for ``kind``. Returns the P1-06 dataclass."""
    return _EXTRACTORS[DocumentKind(kind)](ocr)


def ocr_result_from_dict(data: dict) -> OCRResult:
    """Build an OCRResult from a prototype-schema JSON dict (output/ocr/*.json)."""
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


def dump_document(doc: object) -> str:
    """Serialize a P1-06 dataclass to JSON (money as str, per P1-06 convention)."""
    return json.dumps(dataclasses.asdict(doc), default=str, indent=2)
