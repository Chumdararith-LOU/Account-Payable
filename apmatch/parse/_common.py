"""Shared helpers for the document extractors.

Small block-level heuristics used by more than one extractor. Label variants
stay in the extractor modules (diffable); only the mechanics live here.
"""

from __future__ import annotations

import re
from decimal import Decimal

from apmatch.ocr.engine import OCRResult, TextBlock
from apmatch.parse.coerce import parse_money
from apmatch.parse.spatial import (
    _normalize,
    find_label,
    same_block_value,
    value_after_label,
    value_right_or_below,
)
from apmatch.schema.coercion import to_money

_COMPANY_RE = re.compile(r"(Co\.\s*Ltd\.|Ltd\.|Inc\.)")


def labeled_value(
    blocks: tuple[TextBlock, ...],
    variants: tuple[str, ...],
    max_gap_px: float = 200.0,
) -> str | None:
    """Find the label, then try same-block, right, below; first non-empty value.

    Same-block is tried first because PP-OCRv6 merges label and value into one
    block for header fields (``No.:INV-2026-1123``, ``Date:20-Aug-2026``).
    """
    label = find_label(blocks, variants)
    if label is None:
        return None
    value = same_block_value(label, variants)
    if value is not None:
        return value
    return value_right_or_below(blocks, label.bbox, max_gap_px)


def company_name_fallback(blocks: tuple[TextBlock, ...]) -> str | None:
    """Legacy vendor heuristic: pick a company-name block.

    When two company names appear (buyer + vendor), the vendor is the second
    in source order on invoices and POs. Kept from the legacy prototype.
    """
    names = [b.text.strip() for b in blocks if _COMPANY_RE.search(b.text)]
    if len(names) >= 2:
        return names[1]
    return names[0] if names else None


def labeled_money(
    blocks: tuple[TextBlock, ...],
    variants: tuple[str, ...],
    max_gap_px: float = 200.0,
) -> Decimal | None:
    """value_after_label + parse_money + to_money; None on any failure."""
    value = parse_money(value_after_label(blocks, variants, max_gap_px))
    return to_money(value) if value is not None else None


def labeled_money_at(
    blocks: tuple[TextBlock, ...],
    label_bbox: tuple[float, float, float, float],
    max_gap_px: float = 200.0,
) -> Decimal | None:
    """labeled_money for a caller-supplied label bbox (e.g. find_total_label)."""
    value = parse_money(value_right_or_below(blocks, label_bbox, max_gap_px))
    return to_money(value) if value is not None else None


def find_total_label(blocks: tuple[TextBlock, ...]) -> TextBlock | None:
    """First block containing 'total' but not 'subtotal' (source order).

    'Subtotal' contains 'total' as a substring, so a plain find_label for
    ('Total',) would return the subtotal row.
    """
    for block in blocks:
        text = _normalize(block.text)
        if "total" in text and "subtotal" not in text:
            return block
    return None


def line_items_from_table(ocr: OCRResult) -> tuple:
    """Line items from the first table (invoice/PO layout).

    Columns located by header text (case-insensitive): #, Description, Qty,
    Unit Price, Amount. Robust to column reordering; if the table has no
    header row, falls back to positional (0=#, 1=desc, 2=qty, 3=price,
    4=amount). Unparseable cells become None — the validator flags them.
    """
    from apmatch.parse._table import find_column, parse_table_rows
    from apmatch.parse.coerce import parse_money, parse_qty
    from apmatch.schema.coercion import to_money, to_qty, to_unit_price
    from apmatch.schema.documents import LineItem

    if not ocr.tables:
        return ()
    header, rows = parse_table_rows(ocr.tables[0].html)
    has_header = any("description" in c.lower() for c in header)
    if has_header:
        col_line = find_column(header, "#")
        col_desc = find_column(header, "description")
        col_qty = find_column(header, "qty")
        col_price = find_column(header, "unit price", "price")
        col_amount = find_column(header, "amount")
    else:
        col_line, col_desc, col_qty, col_price, col_amount = 0, 1, 2, 3, 4

    items = []
    for i, row in enumerate(rows, start=1):

        def cell(idx: int | None) -> str | None:
            if idx is None or idx >= len(row):
                return None
            return row[idx]

        line_no = i
        raw_no = cell(col_line)
        if raw_no:
            try:
                line_no = int(raw_no)
            except ValueError:
                pass
        qty = parse_qty(cell(col_qty))
        price = parse_money(cell(col_price))
        amount = parse_money(cell(col_amount))
        items.append(
            LineItem(
                line_no=line_no,
                description=cell(col_desc) or "",
                quantity=to_qty(qty) if qty is not None else None,
                unit_price=to_unit_price(price) if price is not None else None,
                amount=to_money(amount) if amount is not None else None,
            )
        )
    return tuple(items)
