#!/usr/bin/env python3
"""Diagnose batch failures. Re-runs failed cases with verbose output to
identify what the parser couldn't extract.

Measurement instrument for PROD-B1 (template work). Does NOT fix anything —
it categorizes each failure by (a) which field is missing, (b) what OCR
actually produced for that field, (c) the root-cause hypothesis:

  label_not_found               no OCR block contains a known label
  label_found_but_value_missing label present, no value to the right/below
  value_parse_failed            label+value present, but the coerce fn returned None
  table_structure               line items missing (table parse failed / empty)
  other                         anything else

Stdlib only for file/CLI/json. The apmatch OCR/parse imports are the
legitimate heavy dependencies. Runs on the GPU server (one-off container).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import fields, replace
from pathlib import Path

from apmatch.layout.structure import LayoutEngine
from apmatch.ocr.router import OCRRouter
from apmatch.parse import dispatch
from apmatch.parse.coerce import parse_date, parse_document_number, parse_money
from apmatch.parse.spatial import find_label, same_block_value, value_right_or_below

# Known label variants per invoice header field (mirrors apmatch/parse/invoice.py).
FIELD_LABELS = {
    "invoice_number": ("Invoice No", "Invoice Number", "INV No", "No."),
    "vendor_name": ("From (Vendor)", "Bill From", "Supplier"),
    "invoice_date": ("Date",),
    "subtotal": ("Subtotal",),
    "tax_amount": ("VAT", "Tax"),
    "total": ("Total",),
}

# Coerce function per field (for value_parse_failed detection).
FIELD_PARSER = {
    "invoice_number": parse_document_number,
    "invoice_date": parse_date,
    "subtotal": parse_money,
    "tax_amount": parse_money,
    "total": parse_money,
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).casefold()


def _cand(block, matched=None, value=None) -> dict:
    d = {"text": block.text, "bbox": [round(v, 1) for v in block.bbox], "conf": block.conf}
    if matched is not None:
        d["matched"] = matched
    if value is not None:
        d["value"] = value
    return d


def fuzzy_candidates(blocks, variants, min_len=3):
    """Blocks whose normalized text contains a >=min_len-char substring of a variant."""
    out = []
    for b in blocks:
        text = _norm(b.text)
        for v in variants:
            vn = _norm(v)
            for i in range(len(vn) - min_len + 1):
                sub = vn[i:i + min_len]
                if sub and sub in text:
                    out.append(_cand(b, matched=sub))
                    break
            else:
                continue
            break
    return out


def diagnose_field(blocks, field, variants):
    """Categorize why a header field is None. Returns (category, candidates)."""
    label = find_label(blocks, variants)
    if label is None:
        return "label_not_found", fuzzy_candidates(blocks, variants)
    value = same_block_value(label, variants)
    if value is None:
        value = value_right_or_below(blocks, label.bbox)
    if value is None:
        return "label_found_but_value_missing", [_cand(label)]
    parser = FIELD_PARSER.get(field)
    if parser is not None and parser(value) is None:
        return "value_parse_failed", [_cand(label, value=value)]
    return "other", [_cand(label, value=value)]


def main() -> None:
    ap = argparse.ArgumentParser(description="Diagnose batch failures.")
    ap.add_argument("--batch-dir", required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--from-report", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--md", required=True)
    args = ap.parse_args()

    report = json.loads(Path(args.from_report).read_text())
    failed = [c for c in report["cases"] if not c["passed"]]
    with open(args.csv, newline="") as fh:
        rows = {r["case_id"]: r for r in csv.DictReader(fh)}

    print("[init] loading OCR router + layout engine ...", flush=True)
    router = OCRRouter()
    layout = LayoutEngine()
    print("[init] engines ready", flush=True)

    results = []
    for i, case in enumerate(failed, 1):
        case_id = case["case_id"]
        row = rows[case_id]
        inv_rel = (row.get("invoice_file") or "").strip()
        inv_path = Path(args.batch_dir) / inv_rel if inv_rel else None

        if inv_path is None or not inv_path.is_file():
            results.append({"case_id": case_id, "style": case["style"], "expected": case["expected"],
                            "actual_route": case["actual_route"], "missing_fields": [],
                            "field_diag": {}, "sample_ocr_text": "", "note": "invoice file missing"})
            print(f"[{i}/{len(failed)}] {case_id} invoice missing", flush=True)
            continue

        ocr = router.recognize(inv_path)
        ocr = replace(ocr, tables=layout.extract(inv_path))
        invoice = dispatch.extract(dispatch.DocumentKind.INVOICE, ocr)

        missing = [f.name for f in fields(invoice)
                   if getattr(invoice, f.name) is None and f.name in FIELD_LABELS]
        if not invoice.line_items:
            missing.append("line_items")

        field_diag = {}
        for field in missing:
            if field == "line_items":
                field_diag[field] = {"category": "table_structure", "candidates": []}
            else:
                cat, cands = diagnose_field(ocr.text_blocks, field, FIELD_LABELS[field])
                field_diag[field] = {"category": cat, "candidates": cands}

        results.append({
            "case_id": case_id,
            "style": case["style"],
            "expected": case["expected"],
            "actual_route": case["actual_route"],
            "missing_fields": missing,
            "field_diag": field_diag,
            "sample_ocr_text": "\n".join(b.text for b in ocr.text_blocks),
        })
        print(f"[{i}/{len(failed)}] {case_id} missing={missing}", flush=True)

    by_category: dict[str, int] = {}
    by_missing_field: dict[str, int] = {}
    by_style: dict[str, int] = {}
    for r in results:
        by_style[r["style"]] = by_style.get(r["style"], 0) + 1
        for field, diag in r["field_diag"].items():
            by_category[diag["category"]] = by_category.get(diag["category"], 0) + 1
            by_missing_field[field] = by_missing_field.get(field, 0) + 1

    out = {
        "total_failures": len(failed),
        "by_category": by_category,
        "by_missing_field": by_missing_field,
        "by_style": by_style,
        "cases": results,
    }
    Path(args.out).write_text(json.dumps(out, indent=2))
    print(f"[done] wrote {args.out}", flush=True)
    Path(args.md).write_text(render_md(out))
    print(f"[done] wrote {args.md}", flush=True)


def render_md(out: dict) -> str:
    total = out["total_failures"]
    lines = ["# Batch failure diagnostics — 120-case baseline", ""]
    lines += ["## Summary", f"Total failures: {total}", ""]
    if out["by_missing_field"]:
        top = max(out["by_missing_field"], key=out["by_missing_field"].get)
        lines.append(f"Top missing field: {top} ({out['by_missing_field'][top]} cases)")
        lines.append("")
    lines += ["## By missing field", "| Field | Count | % of failures |", "|---|---|---|"]
    for f, n in sorted(out["by_missing_field"].items(), key=lambda x: -x[1]):
        lines.append(f"| {f} | {n} | {n / total * 100:.0f}% |")
    lines.append("")
    meaning = {
        "label_not_found": "No OCR block contains a known label for this field",
        "label_found_but_value_missing": "Label found, no value nearby",
        "value_parse_failed": "Label and value both found, but value couldn't be converted",
        "table_structure": "Line items missing — table parse failed",
        "other": "",
    }
    lines += ["## By failure category", "| Category | Count | Meaning |", "|---|---|---|"]
    for c, n in sorted(out["by_category"].items(), key=lambda x: -x[1]):
        lines.append(f"| {c} | {n} | {meaning.get(c, '')} |")
    lines.append("")
    # style x missing field combos
    combos: dict[tuple, int] = {}
    for case in out["cases"]:
        key = (case["style"], tuple(sorted(case["missing_fields"])))
        combos[key] = combos.get(key, 0) + 1
    lines += ["## By style x missing field (top combos)", "| Style | Missing fields | Count |", "|---|---|---|"]
    for k, n in sorted(combos.items(), key=lambda x: -x[1])[:12]:
        lines.append(f"| {k[0]} | {', '.join(k[1]) or '(none)'} | {n} |")
    lines.append("")
    # concrete examples: one per distinct category, up to 4
    lines += ["## Concrete examples", ""]
    seen_cats: set[str] = set()
    shown = 0
    for case in out["cases"]:
        cats = {d["category"] for d in case["field_diag"].values()}
        if cats <= seen_cats or not case["missing_fields"]:
            continue
        seen_cats |= cats
        shown += 1
        if shown > 4:
            break
        lines.append(f"### Example {shown}: {case['case_id']} ({case['style']})")
        lines.append(f"- Expected: {case['expected']}")
        lines.append(f"- Actual route: {case['actual_route']}")
        lines.append(f"- Missing: {', '.join(case['missing_fields'])}")
        for field, diag in case["field_diag"].items():
            lines.append(f"  - {field}: **{diag['category']}**")
            for c in diag["candidates"][:3]:
                extra = f" (value={c['value']!r})" if "value" in c else ""
                lines.append(f"    - OCR block: {c['text']!r}{extra}")
        lines.append("- What the document shows (raw OCR):")
        lines.append("```")
        lines.append(case["sample_ocr_text"][:1500])
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
