"""GRNI extractor: OCRResult -> GRNI (P1-06 schema). Quantity only.

Total function: given ANY OCRResult (including empty), returns a GRNI.
Undetermined fields are None; the validator (P1-06) decides what is a blocker.
"""

from __future__ import annotations

import contextlib
import json
import sys

from apmatch.ocr.engine import OCRResult
from apmatch.parse._common import company_name_fallback, labeled_value
from apmatch.parse._table import find_column, parse_table_rows
from apmatch.parse.coerce import parse_date, parse_document_number, parse_qty
from apmatch.schema.coercion import to_qty
from apmatch.schema.documents import GRNI, LineItem

GRN_NUMBER_VARIANTS = ("GRN No", "GRNI No", "Delivery No", "No.")
VENDOR_VARIANTS = ("Delivered By (Vendor)", "Vendor", "Supplier")
DATE_VARIANTS = ("Date",)


def _line_items_from_html(ocr: OCRResult) -> tuple[LineItem, ...]:
    """Line items from the first table (GRNI layout: #, Description,
    Qty Ordered, Qty Received, Condition). Quantity is the received
    quantity; 'Qty Received' is matched before bare 'Qty' so the ordered
    column is never picked."""
    if not ocr.tables:
        return ()
    header, rows = parse_table_rows(ocr.tables[0].html)
    col_line = find_column(header, "#")
    col_desc = find_column(header, "description")
    col_qty = find_column(header, "qty received")
    if col_qty is None:
        col_qty = find_column(header, "qty")

    items = []
    for i, row in enumerate(rows, start=1):

        def cell(idx: int | None) -> str | None:
            if idx is None or idx >= len(row):  # noqa: B023 — cell() is invoked within the same iteration
                return None
            return row[idx]  # noqa: B023 — row is the current iteration's row

        line_no = i
        raw_no = cell(col_line)
        if raw_no:
            with contextlib.suppress(ValueError):
                line_no = int(raw_no)
        qty = parse_qty(cell(col_qty))
        items.append(
            LineItem(
                line_no=line_no,
                description=cell(col_desc) or "",
                quantity=to_qty(qty) if qty is not None else None,
            )
        )
    return tuple(items)


def _line_items(ocr: OCRResult) -> tuple[LineItem, ...]:
    """GRNI line items from the best available source.

    Tries the PP-StructureV3 table (preferring 'Qty Received') and a
    text-block rebuild, and returns the more complete one. The text-block path
    covers borderless tables and transposed / shifted tables where the raw OCR
    blocks are still clean.
    """
    from apmatch.parse._common import _completeness_score
    from apmatch.parse._table import DEFAULT_COLUMNS, line_items_from_text_blocks

    html_items = _line_items_from_html(ocr)
    block_items = line_items_from_text_blocks(ocr.text_blocks, DEFAULT_COLUMNS)
    if _completeness_score(html_items) >= _completeness_score(block_items):
        return html_items
    return block_items


def extract_grni(ocr: OCRResult) -> GRNI:
    blocks = ocr.text_blocks

    grn_number = parse_document_number(labeled_value(blocks, GRN_NUMBER_VARIANTS))

    vendor_name = labeled_value(blocks, VENDOR_VARIANTS)
    if vendor_name is None:
        vendor_name = company_name_fallback(blocks)

    grni_date = parse_date(labeled_value(blocks, DATE_VARIANTS))

    return GRNI(
        grn_number=grn_number,
        vendor_name=vendor_name,
        grni_date=grni_date,
        line_items=_line_items(ocr),
    )


if __name__ == "__main__":
    from apmatch.parse.dispatch import dump_document, ocr_result_from_dict

    with open(sys.argv[1]) as f:
        print(dump_document(extract_grni(ocr_result_from_dict(json.load(f)))))
