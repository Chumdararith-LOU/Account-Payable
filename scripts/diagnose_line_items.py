#!/usr/bin/env python3
"""Trace line-item alignment for failing batch cases.

For each failed case:
  1. Run OCR + parse on invoice, PO, GRN (no matching).
  2. Dump the extracted line items from each document.
  3. For EVERY invoice line, find:
     - exact matches in PO / GRN (by normalized description), and
     - if no exact match, the top-3 embedding-similarity candidates + scores.
  4. Categorize the case on the FIRST invoice line the engine would flag.

Measurement instrument for PROD-B1c. Does NOT fix anything. It mirrors the
matching engine's two-tier line-item logic (exact, then embedding similarity
with the SIMILARITY_REVIEW / SIMILARITY_ACCEPT bands) so the categories line
up with the failure codes the engine actually emits.

Usage:
  python scripts/diagnose_line_items.py \
      --batch-dir ./batch-120 \
      --csv ./batch-120/labels.csv \
      --from-report ./reports/batch-b1a.json \
      --out ./reports/line-item-diagnostics.json \
      --md ./docs/LINE_ITEM_DIAGNOSTICS.md
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import replace
from pathlib import Path

from apmatch.embeddings.config import SIMILARITY_ACCEPT, SIMILARITY_REVIEW
from apmatch.embeddings.model import EmbeddingModel
from apmatch.layout.structure import LayoutEngine
from apmatch.matching.config import (
    AMOUNT_TOLERANCE,
    AMOUNT_TOLERANCE_REL,
    QTY_TOLERANCE_ABS,
)
from apmatch.matching.normalize import normalize_text
from apmatch.ocr.router import OCRRouter
from apmatch.parse import dispatch
from apmatch.parse.dispatch import DocumentKind

REVIEW = float(SIMILARITY_REVIEW)
ACCEPT = float(SIMILARITY_ACCEPT)


def _line_dict(li) -> dict:
    return {
        "line_no": li.line_no,
        "description_raw": li.description,
        "description_normalized": normalize_text(li.description),
        "quantity": str(li.quantity) if li.quantity is not None else None,
        "unit_price": str(li.unit_price) if li.unit_price is not None else None,
        "amount": str(li.amount) if li.amount is not None else None,
    }


def _find_line(lines, description: str):
    """First line (source order) whose normalized description matches."""
    target = normalize_text(description)
    for li in lines:
        if normalize_text(li.description) == target:
            return li
    return None


def _scored(model, inv_desc: str, lines):
    """(score, line) for each non-empty candidate, sorted by score desc."""
    inv_text = normalize_text(inv_desc)
    if not inv_text:
        return []
    out = []
    for li in lines:
        cand = normalize_text(li.description)
        if not cand:
            continue
        out.append((model.similarity(inv_text, cand), li))
    out.sort(key=lambda t: (-t[0], t[1].line_no))
    return out


def _top3(model, inv_desc: str, lines, n=3):
    return [
        {"description": li.description, "similarity": round(score, 4)}
        for score, li in _scored(model, inv_desc, lines)[:n]
    ]


def _side_status(model, inv, lines, has_side):
    """Mirror the engine's per-side line lookup.

    Returns (status, matched_line, best_sim, top3) where status is one of:
      "n/a" (no such doc), "exact", "sim_accept", "sim_review", "no_match".
    """
    if not has_side:
        return "n/a", None, None, []
    match = _find_line(lines, inv.description)
    if match is not None:
        return "exact", match, None, []
    scored = _scored(model, inv.description, lines)
    if not scored:
        return "no_match", None, None, []
    best, best_line = scored[0]
    top3 = _top3(model, inv.description, lines)
    if best >= ACCEPT:
        return "sim_accept", best_line, best, top3
    if best >= REVIEW:
        return "sim_review", best_line, best, top3
    return "no_match", best_line, best, top3


def _qty_mismatch(inv, match) -> bool:
    return (
        match is not None
        and inv.quantity is not None
        and match.quantity is not None
        and abs(inv.quantity - match.quantity) > QTY_TOLERANCE_ABS
    )


def _amount_mismatch(inv, po_match) -> bool:
    """Engine rule: inv.amount vs po.quantity * po.unit_price."""
    if po_match is None or inv.amount is None:
        return False
    if po_match.quantity is None or po_match.unit_price is None:
        return False
    po_amount = po_match.quantity * po_match.unit_price
    diff = abs(inv.amount - po_amount)
    max_val = max(abs(inv.amount), abs(po_amount))
    return diff > AMOUNT_TOLERANCE and (max_val == 0 or diff / max_val > AMOUNT_TOLERANCE_REL)


def align_invoice_lines(inv_lines, po_lines, grn_lines, has_po, has_grn, model):
    """Per-line alignment for every invoice line (PO side + GRN side)."""
    out = []
    for inv in inv_lines:
        po_status, po_match, po_best, po_top3 = _side_status(model, inv, po_lines, has_po)
        grn_status, grn_match, grn_best, grn_top3 = _side_status(model, inv, grn_lines, has_grn)

        po_no_match = po_status == "no_match"
        grn_no_match = grn_status == "no_match"
        qty_fail = _qty_mismatch(inv, po_match) or _qty_mismatch(inv, grn_match)
        amount_fail = _amount_mismatch(inv, po_match)

        # A line "fails to align" if either side is a hard no-match, or a
        # matched side has a qty/amount discrepancy. sim_review is a soft
        # match (engine records a warning but the line IS aligned).
        failing = po_no_match or grn_no_match or qty_fail or amount_fail
        if not failing:
            status = "ok"
        elif po_no_match or grn_no_match:
            status = "no_match"
        elif qty_fail:
            status = "qty_mismatch"
        else:
            status = "amount_mismatch"

        out.append({
            "line_no": inv.line_no,
            "description_raw": inv.description,
            "description_normalized": normalize_text(inv.description),
            "quantity": str(inv.quantity) if inv.quantity is not None else None,
            "amount": str(inv.amount) if inv.amount is not None else None,
            "po_status": po_status,
            "po_exact_line": po_match.line_no if po_match else None,
            "po_best_sim": round(po_best, 4) if po_best is not None else None,
            "po_top3": po_top3,
            "grn_status": grn_status,
            "grn_exact_line": grn_match.line_no if grn_match else None,
            "grn_best_sim": round(grn_best, 4) if grn_best is not None else None,
            "grn_top3": grn_top3,
            "status": status,
        })
    return out


def categorize(align):
    """Categorize the case on the first failing invoice line.

    ``align`` is the list from align_invoice_lines. Returns (category, detail).
    Doc-level empty-table categories are applied by the caller (main).
    """
    if not align:
        return "no_invoice_lines", "invoice table parse returned empty"
    for r in align:
        if r["status"] != "ok":
            if r["po_status"] == "no_match" or r["grn_status"] == "no_match":
                # Only the side(s) that actually failed to match count. A soft
                # sim_review/sim_accept on the other side is a match, not a miss.
                failing_sims = []
                if r["po_status"] == "no_match":
                    failing_sims.append(r["po_best_sim"])
                if r["grn_status"] == "no_match":
                    failing_sims.append(r["grn_best_sim"])
                best = max([s for s in failing_sims if s is not None], default=None)
                if best is None or best < REVIEW:
                    return (
                        "similarity_below_review",
                        f"max similarity = {best:.3f}" if best is not None else "no candidates",
                    )
                if best < ACCEPT:
                    return (
                        "similarity_review_band_missed",
                        f"similarity {best:.3f} in review band but no match — BUG",
                    )
                return (
                    "similarity_accept_band_missed",
                    f"similarity {best:.3f} above accept but no match — BUG",
                )
            if r["status"] == "qty_mismatch":
                return "qty_mismatch", f"invoice qty {r['quantity']} differs from matched line"
            if r["status"] == "amount_mismatch":
                return "amount_mismatch", "line amount differs from PO qty*price"
    return "unmatched_other", "no failing line identified (line items align; failure is elsewhere)"


def main() -> None:
    ap = argparse.ArgumentParser(description="Trace line-item alignment for failing cases.")
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

    print("[init] loading OCR router, layout engine, embedding model ...", flush=True)
    router = OCRRouter()
    layout = LayoutEngine()
    model = EmbeddingModel()
    print("[init] engines ready", flush=True)

    def parse_doc(kind, rel):
        if not rel:
            return None
        path = Path(args.batch_dir) / rel
        if not path.is_file():
            return None
        ocr = router.recognize(path)
        ocr = replace(ocr, tables=layout.extract(path))
        return dispatch.extract(kind, ocr)

    results = []
    for i, case in enumerate(failed, 1):
        case_id = case["case_id"]
        row = rows[case_id]
        inv = parse_doc(DocumentKind.INVOICE, row.get("invoice_file"))
        po = parse_doc(DocumentKind.PURCHASE_ORDER, row.get("po_file"))
        grn = parse_doc(DocumentKind.GRNI, row.get("grn_file"))

        inv_lines = inv.line_items if inv else ()
        po_lines = po.line_items if po else ()
        grn_lines = grn.line_items if grn else ()
        has_po = bool((row.get("po_file") or "").strip())
        has_grn = bool((row.get("grn_file") or "").strip())

        align = align_invoice_lines(inv_lines, po_lines, grn_lines, has_po, has_grn, model)
        cat, detail = categorize(align)

        # Doc-level empty-table categories (take precedence over per-line).
        if not inv_lines:
            cat, detail = "no_invoice_lines", "invoice table parse returned empty"
        elif has_po and not po_lines:
            cat, detail = "no_po_lines", "PO table parse returned empty"
        elif has_grn and not grn_lines:
            cat, detail = "no_grn_lines", "GRN table parse returned empty"

        first_fail_code = (case.get("failures") or [{}])[0].get("code")
        results.append({
            "case_id": case_id,
            "style": case["style"],
            "expected": case["expected"],
            "report_first_failure": first_fail_code,
            "has_po": has_po,
            "has_grn": has_grn,
            "invoice_lines": [_line_dict(li) for li in inv_lines],
            "po_lines": [_line_dict(li) for li in po_lines],
            "grn_lines": [_line_dict(li) for li in grn_lines],
            "line_alignment": align,
            "category": cat,
            "detail": detail,
        })
        print(f"[{i}/{len(failed)}] {case_id} -> {cat} (report: {first_fail_code})", flush=True)

    by_category: dict[str, int] = {}
    by_style_x_category: dict[str, dict[str, int]] = {}
    by_report_code: dict[str, int] = {}
    for r in results:
        by_category[r["category"]] = by_category.get(r["category"], 0) + 1
        by_style_x_category.setdefault(r["style"], {})
        by_style_x_category[r["style"]][r["category"]] = (
            by_style_x_category[r["style"]].get(r["category"], 0) + 1
        )
        by_report_code[r["report_first_failure"] or "<none>"] = (
            by_report_code.get(r["report_first_failure"] or "<none>", 0) + 1
        )

    out = {
        "total_cases": len(failed),
        "by_category": by_category,
        "by_style_x_category": by_style_x_category,
        "by_report_first_failure": by_report_code,
        "cases": sorted(results, key=lambda r: r["case_id"]),
    }
    Path(args.out).write_text(json.dumps(out, indent=2))
    print(f"[done] wrote {args.out}", flush=True)
    Path(args.md).write_text(render_md(out))
    print(f"[done] wrote {args.md}", flush=True)


def render_md(out: dict) -> str:
    total = out["total_cases"]
    lines = ["# Line-item alignment diagnostics", ""]
    lines += [
        "## Summary",
        f"- Cases analyzed: {total} (all failed cases from PROD-B1a)",
        "",
    ]
    if out["by_category"]:
        top = max(out["by_category"], key=out["by_category"].get)
        lines.append(
            f"- Dominant line-item category: {top} "
            f"({out['by_category'][top]} cases, {out['by_category'][top] / total * 100:.0f}%)"
        )
        lines.append("")
    lines += ["## By category", "| Category | Count | % of failures |", "|---|---|---|"]
    for cat, n in sorted(out["by_category"].items(), key=lambda x: -x[1]):
        lines.append(f"| {cat} | {n} | {n / total * 100:.0f}% |")
    lines.append("")
    lines += [
        "## Report first-failure code (for correlation)",
        "| First failure code | Count |",
        "|---|---|",
    ]
    for code, n in sorted(out["by_report_first_failure"].items(), key=lambda x: -x[1]):
        lines.append(f"| {code} | {n} |")
    lines.append("")
    lines += ["## By style x category", "| Style | Category | Count |", "|---|---|---|"]
    for style in sorted(out["by_style_x_category"]):
        for cat, n in sorted(out["by_style_x_category"][style].items(), key=lambda x: -x[1]):
            lines.append(f"| {style} | {cat} | {n} |")
    lines.append("")
    lines += ["## Concrete examples", ""]
    shown: dict[str, int] = {}
    for case in out["cases"]:
        cat = case["category"]
        if shown.get(cat, 0) >= 2:
            continue
        shown[cat] = shown.get(cat, 0) + 1
        lines.append(f"### {cat} — {case['case_id']} ({case['style']})")
        lines.append(f"- Report first failure: {case['report_first_failure']}")
        lines.append(f"- Detail: {case['detail']}")
        for r in case["line_alignment"]:
            if r["status"] == "ok":
                continue
            lines.append(
                f"- line {r['line_no']}: {r['description_raw']!r} "
                f"(qty={r['quantity']}, amount={r['amount']}) -> {r['status']}"
            )
            for side in ("po", "grn"):
                st = r[f"{side}_status"]
                if st in ("exact", "sim_accept", "sim_review"):
                    lines.append(f"    {side}: {st} (line {r[f'{side}_exact_line']})")
                elif st == "no_match":
                    lines.append(f"    {side}: no_match (best sim={r[f'{side}_best_sim']})")
                    for c in r[f"{side}_top3"]:
                        lines.append(f"      candidate: {c['description']!r} (sim={c['similarity']})")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
