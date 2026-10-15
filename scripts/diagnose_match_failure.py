"""Diagnose line-item match failures on the four fixture documents.

Runs OCR + layout + parse on each document, prints the extracted line items
(raw OCR text + normalized form), then walks the invoice lines and shows which
PO line each matched (or why none did, with the normalizer's output on both
sides). Read-only: it imports apmatch/ but never modifies it.

Run from the repo root:  python scripts/diagnose_match_failure.py
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from apmatch.layout.structure import LayoutEngine  # noqa: E402 — after sys.path.insert
from apmatch.matching.engine import MatchingEngine  # noqa: E402 — after sys.path.insert
from apmatch.matching.normalize import normalize_text  # noqa: E402 — after sys.path.insert
from apmatch.ocr.router import OCRRouter  # noqa: E402 — after sys.path.insert
from apmatch.parse import dispatch  # noqa: E402 — after sys.path.insert

DOCS = {
    "invoice": ("documents/invoice/INV_2026_1123.png", dispatch.DocumentKind.INVOICE),
    "po": ("documents/po/PO_2026_0451.png", dispatch.DocumentKind.PURCHASE_ORDER),
    "grni": ("documents/grni/GRN_2026_0322.png", dispatch.DocumentKind.GRNI),
    "pard": ("documents/pard/PARD_2026_0210.png", dispatch.DocumentKind.PAYMENT_ADVICE),
}


def recognize_and_parse(router: OCRRouter, layout: LayoutEngine, kind, path: Path):
    """Mirror apmatch.api.pipeline._recognize_and_parse (OCR + tables -> dataclass)."""
    ocr = router.recognize(path)
    ocr = replace(ocr, tables=layout.extract(path))
    return dispatch.extract(kind, ocr)


def print_lines(label: str, doc) -> None:
    print(f"\n=== {label} ===")
    for li in doc.line_items:
        norm = normalize_text(li.description)
        # description is the raw OCR text: the parser copies the table cell
        # verbatim (parse/_common.py line_items_from_table), so raw_ocr_text
        # and description are identical here.
        print(f"  line {li.line_no}:")
        print(f"    description          = {li.description!r}")
        print(f"    raw_ocr_text         = {li.description!r}")
        print(f"    normalized_description = {norm!r}")


def main() -> int:
    router = OCRRouter()
    layout = LayoutEngine()

    docs = {}
    for name, (rel, kind) in DOCS.items():
        docs[name] = recognize_and_parse(router, layout, kind, REPO_ROOT / rel)

    invoice, po, grni, pard = docs["invoice"], docs["po"], docs["grni"], docs["pard"]

    print_lines(f"INVOICE ({invoice.invoice_number})", invoice)
    print_lines(f"PO ({po.po_number})", po)
    print_lines(f"GRNI ({grni.grn_number})", grni)

    # Match analysis: replicate MatchingEngine._find_line — the FIRST PO line
    # whose normalized description equals the invoice line's normalized one.
    print("\n=== MATCH ANALYSIS: each invoice line vs the PO lines ===")
    po_norms = [(li.line_no, li.description, normalize_text(li.description)) for li in po.line_items]
    for inv in invoice.line_items:
        inv_norm = normalize_text(inv.description)
        matched = next(((no, d, n) for no, d, n in po_norms if n == inv_norm), None)
        print(f"\n  INV line {inv.line_no}: {inv.description!r}")
        print(f"    INV normalized: {inv_norm!r}")
        if matched is None:
            print("    -> NO MATCHING PO LINE")
            print("    PO lines (raw -> normalized):")
            for no, d, n in po_norms:
                print(f"      PO line {no}: {d!r} -> {n!r}")
        else:
            print(f"    -> MATCHED PO line {matched[0]}: {matched[1]!r}")
            print(f"       PO normalized: {matched[2]!r}")

    # The real engine's verdict, for the record.
    result = MatchingEngine().match(invoice, po, grni, pard)
    print("\n=== MatchingEngine verdict ===")
    print(f"  outcome={result.outcome.value}  score={result.score}")
    for f in result.failures:
        print(f"  {f.code.value} [{f.severity.value}] {f.location}: expected={f.expected!r} actual={f.actual!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
