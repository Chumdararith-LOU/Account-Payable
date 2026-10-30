#!/usr/bin/env python3
"""Dump the table-parser's view of a document, for PROD-B1c debugging.

For a given case (or a single image), runs OCR + layout and prints:
  - all OCR text blocks (text + bbox)
  - each detected table (HTML + bbox + cell count)
  - the header row of the first table (as cells)
  - the LineItems that line_items_from_table extracts

Read-only: imports apmatch/ but never modifies it.

Usage:
  # one case, all three docs (invoice/PO/GRN) from the batch:
  python scripts/debug_table_parser.py --batch-dir ./batch-120 \
      --csv ./batch-120/labels.csv --case CASE-0001

  # a single image:
  python scripts/debug_table_parser.py --image path/to.png --kind invoice
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import replace
from pathlib import Path

from apmatch.layout.structure import LayoutEngine
from apmatch.ocr.router import OCRRouter
from apmatch.parse._common import line_items_from_table
from apmatch.parse._table import parse_table_rows
from apmatch.parse.dispatch import DocumentKind

_KINDS = {
    "invoice": DocumentKind.INVOICE,
    "po": DocumentKind.PURCHASE_ORDER,
    "grn": DocumentKind.GRNI,
}


def _dump_doc(router, layout, kind, path: Path, label: str) -> None:
    print(f"\n{'=' * 70}\n{label}: {path.name}\n{'=' * 70}")
    ocr = router.recognize(path)
    ocr = replace(ocr, tables=layout.extract(path))

    print(f"=== OCR text blocks ({len(ocr.text_blocks)}) ===")
    for i, b in enumerate(ocr.text_blocks):
        print(f"  [{i}] bbox=({b.bbox[0]:.0f},{b.bbox[1]:.0f},{b.bbox[2]:.0f},{b.bbox[3]:.0f}) {b.text!r}")

    print(f"=== Detected tables ({len(ocr.tables)}) ===")
    for ti, t in enumerate(ocr.tables):
        header, rows = parse_table_rows(t.html)
        ncells = sum(len(r) for r in rows) + (len(header) if header else 0)
        print(f"  Table {ti}: bbox=({t.bbox[0]:.0f},{t.bbox[1]:.0f},{t.bbox[2]:.0f},{t.bbox[3]:.0f}) "
              f"header_cells={len(header)} data_rows={len(rows)} total_cells={ncells}")
        print(f"    HTML:\n{t.html}")

    if ocr.tables:
        header, _ = parse_table_rows(ocr.tables[0].html)
        print(f"=== Header row (first table) ===\n  {header}")
    else:
        print("=== Header row ===\n  (no table detected)")

    items = line_items_from_table(ocr)
    print(f"=== Parsed line items ({len(items)}) ===")
    for li in items:
        print(f"  L{li.line_no}: desc={li.description!r} qty={li.quantity} "
              f"price={li.unit_price} amt={li.amount}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Dump the table-parser's view of a document.")
    ap.add_argument("--batch-dir")
    ap.add_argument("--csv")
    ap.add_argument("--case")
    ap.add_argument("--image")
    ap.add_argument("--kind", choices=sorted(_KINDS))
    args = ap.parse_args()

    router = OCRRouter()
    layout = LayoutEngine()

    if args.image:
        if not args.kind:
            ap.error("--image requires --kind")
        _dump_doc(router, layout, _KINDS[args.kind], Path(args.image), f"{args.kind.upper()}")
        return

    if not (args.batch_dir and args.csv and args.case):
        ap.error("provide either --image/--kind or --batch-dir/--csv/--case")

    with open(args.csv, newline="") as fh:
        row = next(r for r in csv.DictReader(fh) if r["case_id"] == args.case)
    base = Path(args.batch_dir)
    for label, col in (("INVOICE", "invoice_file"), ("PO", "po_file"), ("GRN", "grn_file")):
        rel = (row.get(col) or "").strip()
        if not rel:
            print(f"\n{label}: (missing)")
            continue
        _dump_doc(router, layout, _KINDS[col.replace("_file", "")], base / rel, label)


if __name__ == "__main__":
    main()
