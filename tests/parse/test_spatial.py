"""Spatial primitives: bbox_right_of, bbox_below, find_label, value_after_label."""

from datetime import date

from apmatch.ocr.engine import TextBlock
from apmatch.parse._common import find_total_label
from apmatch.parse.coerce import parse_date
from apmatch.parse.spatial import (
    bbox_below,
    bbox_right_of,
    find_label,
    find_vendor_heuristic,
    value_after_label,
    value_after_label_with_validation,
)


def _b(text: str, x0: float, y0: float, x1: float, y1: float) -> TextBlock:
    return TextBlock(text=text, bbox=(x0, y0, x1, y1))


def test_bbox_right_of():
    label = (100, 100, 200, 140)
    blocks = (
        _b("right", 250, 110, 350, 150),
        _b("far", 390, 110, 490, 150),
        _b("below", 250, 300, 350, 340),
        _b("left", 10, 110, 90, 150),
    )
    out = bbox_right_of(blocks, label)
    assert [b.text for b in out] == ["right", "far"]  # sorted by x-distance


def test_bbox_below():
    label = (100, 100, 200, 140)
    blocks = (
        _b("below", 120, 160, 220, 200),
        _b("far-below", 120, 400, 220, 440),
        _b("right", 300, 110, 400, 150),
    )
    out = bbox_below(blocks, label)
    assert [b.text for b in out] == ["below"]  # far-below exceeds max_gap_px


def test_find_label_exact_match():
    blocks = (_b("Invoice No", 0, 0, 50, 20), _b("INV-1", 60, 0, 120, 20))
    assert find_label(blocks, ("Invoice No",)).text == "Invoice No"


def test_find_label_case_insensitive():
    blocks = (_b("invoice no", 0, 0, 50, 20),)
    assert find_label(blocks, ("Invoice No",)) is not None


def test_find_label_returns_none_when_missing():
    blocks = (_b("Total", 0, 0, 50, 20),)
    assert find_label(blocks, ("Invoice No",)) is None


def test_find_total_label_skips_subtotal():
    # "Subtotal" contains "total" as a substring, so a plain find_label for
    # ("Total",) collides with the subtotal row. The total lookup must use
    # find_total_label, which excludes blocks containing "subtotal".
    subtotal = _b("Subtotal/ ", 100, 100, 200, 140)
    total = _b("TOTAL / NJU", 100, 200, 200, 240)
    blocks = (subtotal, total)  # Subtotal BEFORE Total in source order
    assert find_label(blocks, ("Total",)).text == "Subtotal/ "  # the collision
    assert find_total_label(blocks).text == "TOTAL / NJU"  # the disambiguation


def test_value_after_label_right_first():
    label = _b("Total", 100, 100, 200, 140)
    right = _b("USD 500.00", 250, 110, 400, 150)
    below = _b("USD 999.00", 120, 160, 270, 200)
    assert value_after_label((label, right, below), ("Total",)) == "USD 500.00"


def test_value_after_label_below_fallback():
    label = _b("Total", 100, 100, 200, 140)
    below = _b("USD 999.00", 120, 160, 270, 200)
    assert value_after_label((label, below), ("Total",)) == "USD 999.00"


def test_value_after_label_strips_colon_and_whitespace():
    label = _b("Total", 100, 100, 200, 140)
    right = _b("  : USD 500.00  ", 250, 110, 400, 150)
    assert value_after_label((label, right), ("Total",)) == "USD 500.00"


def test_value_after_label_with_validation_tries_candidates():
    # The "Date" label has a P.O. block to its right, then a real date further
    # right. The legacy value_after_label grabs "P.O.#" (parse_date -> None);
    # the validated version skips it and returns the date that parses.
    label = _b("Date", 100, 100, 200, 140)
    po = _b("P.O.#", 250, 110, 340, 150)
    real = _b("15/08/2025", 390, 110, 500, 150)
    parsed, raw = value_after_label_with_validation(
        (label, po, real), ("Date",), parse_date
    )
    assert parsed == date(2025, 8, 15)
    assert raw == "15/08/2025"


def test_value_after_label_with_validation_falls_through():
    # Label found but no candidate parses -> (None, None).
    label = _b("Date", 100, 100, 200, 140)
    po = _b("P.O.#", 250, 110, 340, 150)
    parsed, raw = value_after_label_with_validation((label, po), ("Date",), parse_date)
    assert parsed is None
    assert raw is None


def test_value_after_label_with_validation_candidate_order():
    # "Invoice Date" is tried before bare "Date"; the specific label's value wins.
    invoice_date = _b("Invoice Date", 100, 100, 250, 140)
    invoice_val = _b("15/08/2025", 300, 110, 420, 150)
    bare_date = _b("Date", 100, 200, 180, 240)
    bare_val = _b("01/01/2026", 230, 210, 350, 250)
    parsed, _ = value_after_label_with_validation(
        (invoice_date, invoice_val, bare_date, bare_val),
        ("Invoice Date", "Date"),
        parse_date,
        candidate_order=("Invoice Date", "Date"),
    )
    assert parsed == date(2025, 8, 15)


def test_value_after_label_with_validation_position_fallback():
    # No label matches; the top-right block carries the value.
    top_right = _b("15/08/2025", 700, 20, 900, 60)
    other = _b("some text", 100, 400, 300, 440)
    parsed, raw = value_after_label_with_validation(
        (top_right, other), ("Date",), parse_date, position_fallback="top-right"
    )
    assert parsed == date(2025, 8, 15)
    assert raw == "15/08/2025"


def test_find_vendor_heuristic_finds_top_company():
    # A legal-suffix company in the top 20% of the page is the vendor.
    title = _b("INVOICE", 100, 10, 300, 40)
    vendor = _b("Acme Corp LLC", 100, 50, 400, 90)
    buyer = _b("Buyer Inc.", 100, 800, 400, 840)  # bottom of page, not top 20%
    found = find_vendor_heuristic((title, vendor, buyer))
    assert found is not None
    assert found.text == "Acme Corp LLC"


def test_find_vendor_heuristic_skips_buyer():
    # A buyer block with a suffix but below the top 20% is not chosen.
    buyer = _b("Buyer Inc.", 100, 800, 400, 840)
    assert find_vendor_heuristic((buyer,)) is None


def test_find_vendor_heuristic_returns_none_if_no_suffix():
    # No legal suffix anywhere -> None (the caller falls back to None).
    blocks = (_b("Sunshine Motors Service", 100, 50, 400, 90), _b("INVOICE", 100, 10, 300, 40))
    assert find_vendor_heuristic(blocks) is None
