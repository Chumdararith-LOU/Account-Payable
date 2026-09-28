"""Spatial primitives: bbox_right_of, bbox_below, find_label, value_after_label."""

from apmatch.ocr.engine import TextBlock
from apmatch.parse._common import find_total_label
from apmatch.parse.spatial import (
    bbox_below,
    bbox_right_of,
    find_label,
    value_after_label,
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
