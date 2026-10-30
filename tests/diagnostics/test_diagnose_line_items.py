"""Self-check for the line-item alignment diagnostic's pure logic.

The script (scripts/diagnose_line_items.py) is a one-off GPU instrument, but its
categorization / alignment helpers are pure and worth pinning down. We load the
script by path (scripts/ is not a package) and drive them with a fake embedding
model so no sentence-transformers import is needed.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from apmatch.schema.documents import LineItem

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "diagnose_line_items.py"


def _load():
    spec = importlib.util.spec_from_file_location("diagnose_line_items", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _li(no, desc, qty="1", price=None, amount=None):
    from decimal import Decimal

    return LineItem(
        line_no=no,
        description=desc,
        quantity=Decimal(qty),
        unit_price=Decimal(price) if price is not None else None,
        amount=Decimal(amount) if amount is not None else None,
    )


class FakeModel:
    """Deterministic similarity: 1.0 for identical normalized text, else 0.0."""

    def similarity(self, a, b):
        return 1.0 if a == b else 0.0


def test_categorize_no_invoice_lines():
    mod = _load()
    cat, _ = mod.categorize([])
    assert cat == "no_invoice_lines"


def test_categorize_exact_match_is_ok():
    mod = _load()
    inv = [_li(1, "widget", "2", "10", "20")]
    po = [_li(1, "widget", "2", "10", "20")]
    grn = [_li(1, "widget", "2")]
    align = mod.align_invoice_lines(inv, po, grn, True, True, FakeModel())
    assert align[0]["status"] == "ok"
    assert align[0]["po_status"] == "exact"
    assert align[0]["grn_status"] == "exact"
    cat, _ = mod.categorize(align)
    assert cat == "unmatched_other"  # nothing failing


def test_categorize_similarity_below_review():
    mod = _load()
    inv = [_li(1, "widget alpha", "1", "10", "10")]
    po = [_li(1, "completely different", "1", "10", "10")]
    grn = [_li(1, "also different", "1")]
    align = mod.align_invoice_lines(inv, po, grn, True, True, FakeModel())
    assert align[0]["po_status"] == "no_match"
    assert align[0]["po_best_sim"] == 0.0
    cat, detail = mod.categorize(align)
    assert cat == "similarity_below_review"
    assert "0.000" in detail


def test_categorize_qty_mismatch():
    mod = _load()
    inv = [_li(1, "widget", "5", "10", "50")]
    po = [_li(1, "widget", "3", "10", "30")]
    grn = [_li(1, "widget", "5")]
    align = mod.align_invoice_lines(inv, po, grn, True, True, FakeModel())
    assert align[0]["status"] == "qty_mismatch"
    cat, _ = mod.categorize(align)
    assert cat == "qty_mismatch"


def test_categorize_amount_mismatch():
    mod = _load()
    # qty matches, but invoice amount != po qty*price
    inv = [_li(1, "widget", "2", "10", "99")]
    po = [_li(1, "widget", "2", "10", "20")]
    grn = [_li(1, "widget", "2")]
    align = mod.align_invoice_lines(inv, po, grn, True, True, FakeModel())
    assert align[0]["status"] == "amount_mismatch"
    cat, _ = mod.categorize(align)
    assert cat == "amount_mismatch"


def test_categorize_review_band_is_soft_match():
    mod = _load()

    class ReviewModel:
        def similarity(self, a, b):
            return 0.6  # in [REVIEW, ACCEPT) -> soft match, not a failure

    inv = [_li(1, "widget", "1", "10", "10")]
    po = [_li(1, "widget-ish", "1", "10", "10")]
    grn = [_li(1, "widget", "1")]
    align = mod.align_invoice_lines(inv, po, grn, True, True, ReviewModel())
    assert align[0]["po_status"] == "sim_review"
    assert align[0]["status"] == "ok"  # review band is a soft match
    cat, _ = mod.categorize(align)
    assert cat == "unmatched_other"


def test_categorize_only_counts_failing_side():
    mod = _load()

    class SplitModel:
        # PO candidate scores 0.4 (below review -> no_match);
        # GRN candidate scores 0.6 (review band -> soft match).
        def similarity(self, a, b):
            return 0.4 if b.startswith("po") else 0.6

    inv = [_li(1, "widget", "1", "10", "10")]
    po = [_li(1, "po-candidate", "1", "10", "10")]
    grn = [_li(1, "grn-candidate", "1")]
    align = mod.align_invoice_lines(inv, po, grn, True, True, SplitModel())
    assert align[0]["po_status"] == "no_match"
    assert align[0]["grn_status"] == "sim_review"
    assert align[0]["status"] == "no_match"  # PO side failed
    cat, _ = mod.categorize(align)
    # The GRN soft-match must not leak into the PO-side failure.
    assert cat == "similarity_below_review"


def test_top3_reports_candidates():
    mod = _load()
    inv = [_li(1, "widget", "1", "10", "10")]
    po = [_li(1, "a", "1"), _li(2, "b", "1"), _li(3, "c", "1"), _li(4, "d", "1")]
    grn = []
    align = mod.align_invoice_lines(inv, po, grn, True, False, FakeModel())
    assert len(align[0]["po_top3"]) == 3
    assert all(c["similarity"] == 0.0 for c in align[0]["po_top3"])
