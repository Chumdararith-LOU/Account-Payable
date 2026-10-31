#!/usr/bin/env python3
"""Diagnose clean-invoice (expected MATCH) batch failures.

Runs parse -> validate -> match (no routing, no DB) over every
expected-MATCH case in the labeled batch and dumps the extracted
documents side by side, so a failure can be attributed to the invoice
side, the PO/GRNI side, or a shared mis-read.

The raw invoice OCR (PaddleOCR text blocks) is dumped to
output/ocr/INV_<case_id>.json for every case, so a flagged case can be
inspected at the block level without re-running OCR.

Usage (on the GPU server):
    python scripts/diagnose_clean_failures.py \
        --batch-dir "documents/Sample 3/batch-clean-usd-khr-200-cases" \
        --csv "documents/Sample 3/batch-clean-usd-khr-200-cases/labels.csv" \
        --out reports/clean-failures-<date>.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path

from apmatch.embeddings.model import EmbeddingModel
from apmatch.layout.structure import LayoutEngine
from apmatch.matching.engine import MatchingEngine
from apmatch.ocr.engine import OCRResult, to_prototype_json
from apmatch.ocr.router import OCRRouter
from apmatch.parse import dispatch
from apmatch.validation.arithmetic import validate_invoice
from scripts.run_batch import DOC_FIELDS, load_cases


def load_clean_cases(
    csv_path: Path, batch_dir: Path, style: str | None = None, limit: int | None = None
) -> list[dict]:
    """Expected-MATCH cases from the labeled batch (run_batch's loader + filter)."""
    rows = load_cases(csv_path, style, limit)
    return [r for r in rows if (r.get("expected_status") or "").strip() == "MATCH"]


def _recognize(router, layout, kind, path: Path) -> tuple[OCRResult, object]:
    """One OCR pass per document: (raw OCRResult, parsed dataclass).

    Mirrors apmatch.api.pipeline._recognize_and_parse (which returns the
    parsed document only) but keeps the OCRResult for the output/ocr/ dump.
    """
    ocr_result = router.recognize(path)
    tables = layout.extract(path)
    ocr_result = replace(ocr_result, tables=tables)
    return ocr_result, dispatch.extract(kind, ocr_result)


def _s(v):
    """Decimal/date -> str for JSON; None passes through."""
    return None if v is None else str(v)


def _line_dict(li) -> dict:
    return {
        "line_no": li.line_no,
        "description": li.description,
        "quantity": _s(li.quantity),
        "unit_price": _s(li.unit_price),
        "amount": _s(li.amount),
    }


def _invoice_dict(inv) -> dict:
    return {
        "invoice_number": inv.invoice_number,
        "vendor_name": inv.vendor_name,
        "invoice_date": _s(inv.invoice_date),
        "currency": inv.currency,
        "subtotal": _s(inv.subtotal),
        "tax_amount": _s(inv.tax_amount),
        "total": _s(inv.total),
        "line_items": [_line_dict(li) for li in inv.line_items],
    }


def _po_dict(po) -> dict:
    return {
        "po_number": po.po_number,
        "vendor_name": po.vendor_name,
        "po_date": _s(po.po_date),
        "currency": po.currency,
        "total": _s(po.total),
        "line_items": [_line_dict(li) for li in po.line_items],
    }


def _grni_dict(grni) -> dict:
    return {
        "grn_number": grni.grn_number,
        "vendor_name": grni.vendor_name,
        "grni_date": _s(grni.grni_date),
        "line_items": [_line_dict(li) for li in grni.line_items],
    }


def _pard_dict(pard) -> dict:
    return {
        "pard_number": pard.pard_number,
        "invoice_number": pard.invoice_number,
        "amount": _s(pard.amount),
        "payment_date": _s(pard.payment_date),
    }


def diagnose_one(case: dict, engines: dict, batch_dir: Path) -> dict:
    """Run parse -> validate -> match for one case; return the side-by-side dict."""
    case_id = case.get("case_id", "")
    style = case.get("style", "")

    paths: dict[str, Path | None] = {}
    for col, kwarg in DOC_FIELDS.items():
        rel = (case.get(col) or "").strip()
        paths[kwarg] = (batch_dir / rel) if rel else None

    router, layout = engines["router"], engines["layout"]

    invoice_ocr = None
    invoice = None
    if paths["invoice_path"] is not None:
        invoice_ocr, invoice = _recognize(
            router, layout, dispatch.DocumentKind.INVOICE, paths["invoice_path"]
        )
    po = (
        _recognize(router, layout, dispatch.DocumentKind.PURCHASE_ORDER, paths["po_path"])[1]
        if paths["po_path"] is not None
        else None
    )
    grni = (
        _recognize(router, layout, dispatch.DocumentKind.GRNI, paths["grni_path"])[1]
        if paths["grni_path"] is not None
        else None
    )
    pard = (
        _recognize(router, layout, dispatch.DocumentKind.PAYMENT_ADVICE, paths["pard_path"])[1]
        if paths["pard_path"] is not None
        else None
    )

    # Raw invoice OCR for block-level inspection of flagged cases.
    if invoice_ocr is not None:
        ocr_dir = Path("output/ocr")
        ocr_dir.mkdir(parents=True, exist_ok=True)
        (ocr_dir / f"INV_{case_id}.json").write_text(
            json.dumps(to_prototype_json(invoice_ocr), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    validation = validate_invoice(invoice)
    match = MatchingEngine(embedding_model=engines["embedding_model"]).match(invoice, po, grni, pard)

    result = {
        "case_id": case_id,
        "style": style,
        "invoice_extracted": _invoice_dict(invoice) if invoice is not None else None,
        "po_extracted": _po_dict(po) if po is not None else None,
        "grni_extracted": _grni_dict(grni) if grni is not None else None,
        "pard_extracted": _pard_dict(pard) if pard is not None else None,
        "validation_failures": [
            {"code": f.code.value, "severity": f.severity.value, "location": f.location}
            for f in validation.checks_failed
        ],
        "match_failures": [
            {
                "code": f.code.value,
                "severity": f.severity.value,
                "location": f.location,
                "expected": f.expected,
                "actual": f.actual,
            }
            for f in match.failures
        ],
    }
    result["root_cause"] = categorize(result)
    return result


def categorize(r: dict) -> str:
    """Single root-cause label per case. Priority order: first match wins."""
    inv = r["invoice_extracted"]
    vf = {f["code"] for f in r["validation_failures"]}
    mf = {f["code"] for f in r["match_failures"]}
    if not inv or not inv["line_items"]:
        return "invoice_no_line_items"
    if "MISSING_REQUIRED_FIELD" in vf:
        # separate header vs line
        line_missing = any(
            "line" in f["location"] for f in r["validation_failures"]
            if f["code"] == "MISSING_REQUIRED_FIELD"
        )
        return "line_items_partial" if line_missing else "header_missing"
    if "LINE_AMOUNT_MISMATCH" in mf:
        return "line_amount_mismatch"
    if "QTY_MISMATCH" in mf:
        return "qty_mismatch"
    if "NO_MATCHING_PO_LINE" in mf:
        return "no_match_po"
    if "NO_MATCHING_GRNI_LINE" in mf:
        return "no_match_grni"
    if "VENDOR_MISMATCH" in mf:
        return "vendor_mismatch"
    if "CURRENCY_MISMATCH" in mf:
        return "currency_mismatch"
    if "UNIT_PRICE_MISMATCH" in mf:
        return "price_mismatch"
    if "PARD_AMOUNT_MISMATCH" in mf:
        return "pard_amount_mismatch"
    return "other"


def _print_example(r: dict) -> None:
    print(f"\n--- example: {r['case_id']} (style={r['style']}) ---")
    for name in ("invoice_extracted", "po_extracted", "grni_extracted"):
        doc = r.get(name)
        if doc is None:
            print(f"  {name}: <missing>")
            continue
        number = doc.get("invoice_number") or doc.get("po_number") or doc.get("grn_number")
        print(f"  {name}: number={number} currency={doc.get('currency')} total={doc.get('total')}")
        for li in doc["line_items"]:
            print(
                f"    line {li['line_no']}: {li['description'][:60]!r} "
                f"qty={li['quantity']} price={li['unit_price']} amount={li['amount']}"
            )
    print("  validation failures (first 3):")
    for f in r["validation_failures"][:3]:
        print(f"    {f['code']} [{f['severity']}] {f['location']}")
    print("  match failures (first 3):")
    for f in r["match_failures"][:3]:
        print(f"    {f['code']} [{f['severity']}] {f['location']} expected={f['expected']!r} actual={f['actual']!r}")


def print_summary(all_results: list[dict]) -> None:
    print("\n" + "=" * 70)
    print(f"ROOT-CAUSE COUNTS  ({len(all_results)} clean cases)")
    print("=" * 70)
    counts = Counter(r["root_cause"] for r in all_results)
    for cause, n in counts.most_common():
        print(f"  {cause:28} {n}")

    print("\nPER-STYLE ROOT CAUSE")
    print("-" * 70)
    by_style = Counter((r["style"], r["root_cause"]) for r in all_results)
    for (style, cause), n in sorted(by_style.items(), key=lambda t: (t[0][0] or "", t[0][1])):
        print(f"  {style or '?':6} {cause:28} {n}")

    print("\n" + "=" * 70)
    print("EXAMPLE CASES (top 3 root causes)")
    print("=" * 70)
    for cause, _n in counts.most_common(3):
        ex = next(r for r in all_results if r["root_cause"] == cause)
        _print_example(ex)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Diagnose expected-MATCH batch failures.")
    ap.add_argument("--batch-dir", required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--style", default=None)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)

    batch_dir = Path(args.batch_dir)
    cases = load_clean_cases(Path(args.csv), batch_dir, args.style, args.limit)
    if not cases:
        print("error: no expected-MATCH cases matched the filter", file=sys.stderr)
        return 2

    # Heavy engines loaded ONCE, shared across cases.
    print("[init] loading OCR router, layout engine, embedding model ...", flush=True)
    t0 = time.time()
    engines = {
        "router": OCRRouter(),
        "layout": LayoutEngine(),
        "embedding_model": EmbeddingModel(),
    }
    print(f"[init] engines ready in {time.time() - t0:.1f}s", flush=True)

    results: list[dict] = []
    for i, case in enumerate(cases, start=1):
        case_id = case.get("case_id", f"row{i}")
        t_case = time.time()
        try:
            r = diagnose_one(case, engines, batch_dir)
        except Exception as e:  # keep going on a per-case crash
            r = {
                "case_id": case_id, "style": case.get("style", ""),
                "invoice_extracted": None, "po_extracted": None,
                "grni_extracted": None, "pard_extracted": None,
                "validation_failures": [], "match_failures": [],
                "root_cause": f"error: {type(e).__name__}: {str(e)[:120]}",
            }
        results.append(r)
        print(f"[{i}/{len(cases)}] {case_id} -> {r['root_cause']} {time.time() - t_case:.1f}s", flush=True)

    print_summary(results)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
