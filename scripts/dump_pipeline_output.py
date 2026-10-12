"""Dump a canonical JSON representation of the pipeline's output for a set of
input documents. Used to compare Mac vs server output (EMB-01g).

Usage:
  python scripts/dump_pipeline_output.py \
    --invoice documents/invoice/INV_2026_1123.png \
    --po documents/po/PO_2026_0451.png \
    --grni documents/grni/GRN_2026_0322.png \
    --pard documents/pard/PARD_2026_0210.png \
    --extra documents/invoice/invoice.png \
    --out /tmp/pipeline_dump.json

Output is canonical JSON: sorted keys, Decimals as strings, dates as ISO 8601,
bbox coordinates rounded to int, confidence rounded to 2 dp.

The extra images (--extra) are OCR'd (and table-extracted) individually but
not fed into the pipeline (parsed=null). They let us compare OCR output
across more images.

Read-only: imports apmatch/ but never modifies it.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import platform
import sys
from datetime import date
from decimal import Decimal
from dataclasses import replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import paddle  # noqa: E402  (version only)

from apmatch.audit.hashing import compute_input_hash  # noqa: E402
from apmatch.layout.structure import LayoutEngine  # noqa: E402
from apmatch.matching.engine import MatchingEngine  # noqa: E402
from apmatch.ocr.router import OCRRouter  # noqa: E402
from apmatch.parse import dispatch  # noqa: E402
from apmatch.scoring.router import decide  # noqa: E402
from apmatch.validation.arithmetic import validate_invoice  # noqa: E402


def _bbox_ints(bbox) -> list[int]:
    return [int(round(v)) for v in bbox]


def _scalar(v):
    """Render a document field canonically: Decimal -> str, date -> ISO, None -> None."""
    if v is None:
        return None
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, date):
        return v.isoformat()
    return v


def _line_item_dict(li) -> dict:
    return {
        "line_no": li.line_no,
        "description": li.description,
        "quantity": str(li.quantity) if li.quantity is not None else None,
        "unit_price": str(li.unit_price) if li.unit_price is not None else None,
        "amount": str(li.amount) if li.amount is not None else None,
        "unit_of_measure": li.unit_of_measure,
    }


def _parsed_dict(kind: str, doc) -> dict:
    names = [f.name for f in dataclasses.fields(doc)]
    fields = {
        f.name: _scalar(getattr(doc, f.name))
        for f in dataclasses.fields(doc)
        if f.name != "line_items"
    }
    if "line_items" in names:  # PaymentAdvice has no lines
        fields["line_items"] = sorted(
            (_line_item_dict(li) for li in doc.line_items), key=lambda x: x["line_no"]
        )
    return {"kind": kind, "fields": fields}


def _doc_dict(path: str, ocr, tables, parsed) -> dict:
    return {
        "path": path,
        "ocr": {
            "text_blocks": [
                {
                    "text": b.text,
                    "bbox": _bbox_ints(b.bbox),
                    "conf": round(b.conf, 2) if b.conf is not None else None,
                }
                for b in ocr.text_blocks
            ],
        },
        "tables": [{"html": t.html, "bbox": _bbox_ints(t.bbox)} for t in tables],
        "parsed": parsed,
    }


def _failures_dict(failures) -> list[dict]:
    return [
        {
            "code": f.code.value,
            "severity": f.severity.value,
            "location": f.location,
            "expected": f.expected,
            "actual": f.actual,
            "delta": f.delta,
        }
        for f in failures
    ]


def _host_label(explicit: str | None) -> str:
    if explicit:
        return explicit
    return "mac" if sys.platform == "darwin" else "server"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--invoice", required=True)
    p.add_argument("--po", default=None)
    p.add_argument("--grni", default=None)
    p.add_argument("--pard", default=None)
    p.add_argument("--extra", action="append", default=[], help="repeatable")
    p.add_argument("--out", required=True)
    p.add_argument("--host", default=None, help="label for the environment section (default: auto)")
    args = p.parse_args()

    router = OCRRouter()
    layout = LayoutEngine()
    try:
        documents = []
        parsed_docs = {}
        for label, path, kind in (
            ("invoice", args.invoice, dispatch.DocumentKind.INVOICE),
            ("po", args.po, dispatch.DocumentKind.PURCHASE_ORDER),
            ("grni", args.grni, dispatch.DocumentKind.GRNI),
            ("pard", args.pard, dispatch.DocumentKind.PAYMENT_ADVICE),
        ):
            if path is None:
                continue
            ocr = router.recognize(Path(path))
            tables = layout.extract(Path(path))
            doc = dispatch.extract(kind, replace(ocr, tables=tables))
            parsed_docs[label] = doc
            documents.append(_doc_dict(path, ocr, tables, _parsed_dict(label, doc)))

        for path in args.extra:
            ocr = router.recognize(Path(path))
            tables = layout.extract(Path(path))
            documents.append(_doc_dict(path, ocr, tables, None))

        invoice = parsed_docs.get("invoice")
        po = parsed_docs.get("po")
        grni = parsed_docs.get("grni")
        pard = parsed_docs.get("pard")

        validation = validate_invoice(invoice)
        match = MatchingEngine().match(invoice, po, grni, pard)
        decision = decide(validation, match, ocr_confidence=None)

        data = {
            "environment": {
                "host": _host_label(args.host),
                "paddle_version": paddle.__version__,
                "python_version": platform.python_version(),
            },
            "documents": documents,
            "pipeline": {
                "validation": {
                    "ok": validation.ok,
                    "checks_failed": _failures_dict(validation.checks_failed),
                },
                "match": {
                    "outcome": match.outcome.value,
                    "score": f"{match.score:.4f}",
                    "failures": _failures_dict(match.failures),
                },
                "decision": {
                    "route": decision.route.value,
                    "reason": decision.reason.value,
                    "score": f"{decision.score.value:.4f}",
                },
                "input_hash": compute_input_hash(invoice, po, grni, pard),
            },
        }
    finally:
        router.close()
        layout.close()

    out = Path(args.out)
    out.write_text(json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out} ({len(documents)} documents)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
