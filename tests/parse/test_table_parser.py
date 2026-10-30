"""Tests for the table-parser fixes (PROD-B1c).

Covers:
  - header-driven column mapping (Fix 1): canonical columns by casefolded
    substring, unknown columns skipped, positional fallback when no header maps.
  - text-block table fallback (Fix 2/3): borderless tables (zero detected
    tables) and garbage / transposed HTML tables fall back to the clean OCR
    text blocks.
"""

from __future__ import annotations

from decimal import Decimal

from apmatch.ocr.engine import OCRResult, Table, TextBlock
from apmatch.parse._common import line_items_from_table
from apmatch.parse._table import line_items_from_text_blocks
from apmatch.parse.invoice import extract_invoice


def _ocr(blocks=(), html=None):
    tables = (Table(html=html, bbox=(0, 0, 0, 0)),) if html else ()
    return OCRResult(source_file="t", text_blocks=tuple(blocks), tables=tables)


def test_column_mapping_by_header_name():
    ocr = _ocr(html=(
        "<table><tr><td>Description</td><td>Qty</td><td>Item Rate</td><td>Amount</td></tr>"
        "<tr><td>Widget</td><td>2</td><td>100.00</td><td>200.00</td></tr>"
        "<tr><td>Gadget</td><td>1</td><td>50.00</td><td>50.00</td></tr></table>"
    ))
    items = line_items_from_table(ocr)
    assert len(items) == 2
    assert items[0].description == "Widget"
    assert items[0].quantity == Decimal("2.0000")
    assert items[0].unit_price == Decimal("100.0000")
    assert items[0].amount == Decimal("200.00")
    assert items[1].description == "Gadget"
    assert items[1].amount == Decimal("50.00")


def test_column_mapping_skips_unknown_columns():
    # HSN (Indian tax code) is not a canonical column and must be ignored.
    ocr = _ocr(html=(
        "<table><tr><td>Item Description</td><td>HSN</td><td>Qty</td>"
        "<td>Item Rate</td><td>Amount</td></tr>"
        "<tr><td>LED Bulb</td><td>853950</td><td>18</td><td>1020.00</td><td>19535.04</td></tr></table>"
    ))
    items = line_items_from_table(ocr)
    assert len(items) == 1
    assert items[0].description == "LED Bulb"
    assert items[0].quantity == Decimal("18.0000")
    assert items[0].unit_price == Decimal("1020.0000")
    assert items[0].amount == Decimal("19535.04")


def test_column_mapping_discount_not_quantity():
    # "Discount" must NOT classify as quantity (the substring "count" would
    # false-match). It is an unknown column and is skipped.
    ocr = _ocr(html=(
        "<table><tr><td>Description</td><td>Qty</td><td>Discount</td>"
        "<td>Amount</td></tr>"
        "<tr><td>Widget</td><td>2</td><td>10.00</td><td>200.00</td></tr></table>"
    ))
    items = line_items_from_table(ocr)
    assert len(items) == 1
    assert items[0].description == "Widget"
    assert items[0].quantity == Decimal("2.0000")
    assert items[0].amount == Decimal("200.00")


def test_column_mapping_positional_fallback():
    # Header row has no recognizable column names -> positional (1=desc, 2=qty,
    # 3=price, 4=amount). The first row is the (unrecognized) header.
    ocr = _ocr(html=(
        "<table><tr><td>A</td><td>B</td><td>C</td><td>D</td><td>E</td></tr>"
        "<tr><td>1</td><td>Widget</td><td>2</td><td>100.00</td><td>200.00</td></tr></table>"
    ))
    items = line_items_from_table(ocr)
    assert len(items) == 1
    assert items[0].description == "Widget"
    assert items[0].quantity == Decimal("2.0000")
    assert items[0].unit_price == Decimal("100.0000")
    assert items[0].amount == Decimal("200.00")


def _borderless_blocks():
    # 5 rows (1 header + 4 data), 3 columns each: Description | Qty | Amount.
    rows = [
        ("Description", "Qty", "Amount"),
        ("Widget", "2", "200.00"),
        ("Gadget", "1", "50.00"),
        ("Doohickey", "3", "300.00"),
        ("Thingamajig", "4", "400.00"),
    ]
    blocks = []
    for r, (c0, c1, c2) in enumerate(rows):
        y = 100 + r * 50
        blocks.append(TextBlock(text=c0, bbox=(100, y, 300, y + 30)))
        blocks.append(TextBlock(text=c1, bbox=(400, y, 500, y + 30)))
        blocks.append(TextBlock(text=c2, bbox=(600, y, 800, y + 30)))
    return blocks


def test_line_items_from_text_blocks_borderless():
    items = line_items_from_text_blocks(_borderless_blocks())
    assert len(items) == 4
    assert items[0].description == "Widget"
    assert items[0].quantity == Decimal("2.0000")
    assert items[0].amount == Decimal("200.00")
    assert [li.description for li in items] == [
        "Widget", "Gadget", "Doohickey", "Thingamajig",
    ]


def test_line_items_from_text_blocks_no_header():
    # Header row has no recognizable column names -> no lines (no positional
    # guess: column order varies by style, so guessing would mis-assign).
    blocks = [
        TextBlock(text="X", bbox=(100, 100, 300, 130)),
        TextBlock(text="Y", bbox=(400, 100, 500, 130)),
        TextBlock(text="Z", bbox=(600, 100, 800, 130)),
        TextBlock(text="Widget", bbox=(100, 150, 300, 180)),
        TextBlock(text="2", bbox=(400, 150, 500, 180)),
        TextBlock(text="200.00", bbox=(600, 150, 800, 180)),
    ]
    assert line_items_from_text_blocks(blocks) == ()


def test_invoice_extraction_uses_text_block_fallback():
    # No detected tables, but tabular text blocks -> extract_invoice still
    # returns line items (the us/in borderless case).
    ocr = _ocr(blocks=_borderless_blocks())
    inv = extract_invoice(ocr)
    assert len(inv.line_items) == 4
    assert inv.line_items[0].description == "Widget"
    assert inv.line_items[0].quantity == Decimal("2.0000")


def test_garbage_table_falls_back_to_text_blocks():
    # A transposed / shifted HTML table (garbage) + clean text blocks: the
    # text-block result (real descriptions) wins over the HTML result (numeric
    # descriptions).
    garbage = (
        "<table><tr><td></td><td>'</td><td>一</td></tr>"
        "<tr><td>17</td><td>3</td><td>1</td></tr></table>"
    )
    ocr = _ocr(blocks=_borderless_blocks(), html=garbage)
    items = line_items_from_table(ocr)
    assert len(items) == 4
    assert items[0].description == "Widget"
    assert items[0].quantity == Decimal("2.0000")
