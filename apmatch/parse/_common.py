"""Shared helpers for the document extractors.

Small block-level heuristics used by more than one extractor. Label variants
stay in the extractor modules (diffable); only the mechanics live here.
"""

from __future__ import annotations

import contextlib
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


def find_total_label(
    blocks: tuple[TextBlock, ...],
    exclude: tuple[str, ...] = ("subtotal",),
) -> TextBlock | None:
    """First block containing 'total' but none of the ``exclude`` substrings.

    'Subtotal' contains 'total' as a substring, so a plain find_label for
    ('Total',) would return the subtotal row. Templates can extend the
    exclusion list (e.g. "Sub Total") via ``exclude``.
    """
    for block in blocks:
        text = _normalize(block.text)
        if "total" in text and not any(_normalize(ex) in text for ex in exclude):
            return block
    return None


def _items_from_html(html: str, columns: dict) -> tuple:
    """Line items from a table's HTML, columns located by header text.

    Each header cell is classified to a canonical column (description /
    quantity / price / amount); unmapped columns (HSN, Discount, Condition,
    ...) are skipped. A positional fallback (1=desc, 2=qty, 3=price, 4=amount)
    is used only when NO header cell maps at all.
    """
    from apmatch.parse._table import classify_header_cell, parse_table_rows
    from apmatch.parse.coerce import parse_money, parse_qty
    from apmatch.schema.coercion import to_money, to_qty, to_unit_price
    from apmatch.schema.documents import LineItem

    header, rows = parse_table_rows(html)
    col_idx: dict[str, int] = {}
    for i, cell_text in enumerate(header):
        col = classify_header_cell(cell_text, columns)
        if col is not None and col not in col_idx:
            col_idx[col] = i
    if not col_idx:
        col_idx = {"description": 1, "quantity": 2, "price": 3, "amount": 4}
    col_line = next(
        (i for i, c in enumerate(header) if c.strip().casefold() in ("#", "no", "no.", "sl", "sl.")),
        None,
    )

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
        qty = parse_qty(cell(col_idx.get("quantity")))
        price = parse_money(cell(col_idx.get("price")))
        amount = parse_money(cell(col_idx.get("amount")))
        items.append(
            LineItem(
                line_no=line_no,
                description=cell(col_idx.get("description")) or "",
                quantity=to_qty(qty) if qty is not None else None,
                unit_price=to_unit_price(price) if price is not None else None,
                amount=to_money(amount) if amount is not None else None,
            )
        )
    return tuple(items)


def _completeness_score(items) -> int:
    """Count lines with a real (non-numeric) description AND a qty or amount.

    Used to pick the better of the HTML-table and text-block results: a
    garbage / transposed table yields empty or numeric descriptions and scores
    low, while the clean text blocks score high.
    """
    n = 0
    for li in items:
        d = (li.description or "").strip()
        if not d or re.fullmatch(r"[\d.,]+", d):
            continue
        if li.quantity is not None or li.amount is not None:
            n += 1
    return n


def line_items_from_table(ocr: OCRResult, template=None) -> tuple:
    """Line items for an invoice/PO, from the best available source.

    Tries the PP-StructureV3 table (header-driven column mapping) and a
    text-block rebuild, and returns the more complete one. The text-block path
    covers borderless tables (zero detected tables) and transposed / shifted
    tables (garbage HTML) where the raw OCR blocks are still clean.
    """
    from apmatch.parse._table import DEFAULT_COLUMNS, line_items_from_text_blocks

    columns = DEFAULT_COLUMNS
    if template is not None and getattr(template.line_items, "columns", None):
        columns = template.line_items.columns
    html_items = _items_from_html(ocr.tables[0].html, columns) if ocr.tables else ()
    block_items = line_items_from_text_blocks(ocr.text_blocks, columns)
    if _completeness_score(html_items) >= _completeness_score(block_items):
        return html_items
    return block_items
