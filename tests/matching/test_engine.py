from datetime import date
from decimal import Decimal

from apmatch.matching.engine import MatchingEngine
from apmatch.matching.result import MatchCode, Outcome
from apmatch.schema.documents import GRNI, Invoice, LineItem, PaymentAdvice, PurchaseOrder
from apmatch.validation.result import Severity

ENGINE = MatchingEngine()


def _line(no, desc, qty, price=None, amount=None):
    return LineItem(
        line_no=no,
        description=desc,
        quantity=Decimal(qty),
        unit_price=Decimal(price) if price is not None else None,
        amount=Decimal(amount) if amount is not None else None,
    )


def _invoice(lines=None, vendor="Mekong Supplies Co., Ltd.", currency="USD", total="1100.00", inv_date=date(2026, 8, 20)):
    if lines is None:
        lines = (
            _line(1, "Office Chair", "10", "45.00", "450.00"),
            _line(2, "Desk Lamp", "20", "12.50", "250.00"),
            _line(3, "Whiteboard", "5", "60.00", "300.00"),
        )
    return Invoice("INV-1", vendor, inv_date, currency, Decimal("1000.00"), Decimal("100.00"), Decimal(total), lines)


def _po(lines=None, vendor="Mekong Supplies Co., Ltd.", currency=None):
    if lines is None:
        lines = (
            _line(1, "Office Chair", "10", "45.00"),
            _line(2, "Desk Lamp", "20", "12.50"),
            _line(3, "Whiteboard", "5", "60.00"),
        )
    return PurchaseOrder("PO-1", vendor, date(2026, 8, 15), Decimal("1000.00"), lines, currency)


def _grni(lines=None, vendor="Mekong Supplies Co., Ltd."):
    if lines is None:
        lines = (_line(1, "Office Chair", "10"), _line(2, "Desk Lamp", "20"), _line(3, "Whiteboard", "5"))
    return GRNI("GRN-1", vendor, date(2026, 8, 19), lines)


def _pard(amount="1100.00", pard_date=date(2026, 8, 25), currency=None):
    return PaymentAdvice("PARD-1", "INV-1", Decimal(amount), pard_date, "REF", currency)


def _codes(result):
    return [f.code for f in result.failures]


# --- Missing-document short-circuits ---------------------------------------


def test_po_missing_returns_pending():
    r = ENGINE.match(_invoice(), None, _grni(), _pard())
    assert r.outcome is Outcome.PENDING_INFO
    assert r.score == 0.0
    assert _codes(r) == [MatchCode.PO_MISSING]


def test_grni_missing_returns_pending():
    r = ENGINE.match(_invoice(), _po(), None, _pard())
    assert r.outcome is Outcome.PENDING_INFO
    assert r.score == 0.0
    assert _codes(r) == [MatchCode.GRNI_MISSING]


def test_pard_missing_returns_pending():
    r = ENGINE.match(_invoice(), _po(), _grni(), None)
    assert r.outcome is Outcome.PENDING_INFO
    assert r.score == 0.0
    assert _codes(r) == [MatchCode.PARD_MISSING]


def test_all_present_does_not_short_circuit():
    r = ENGINE.match(_invoice(), _po(), _grni(), _pard())
    assert r.outcome is not Outcome.PENDING_INFO


# --- Header checks ---------------------------------------------------------


def test_vendor_mismatch():
    r = ENGINE.match(_invoice(), _po(vendor="Other Vendor Co."), _grni(), _pard())
    assert MatchCode.VENDOR_MISMATCH in _codes(r)
    assert r.outcome is Outcome.DISCREPANCY


def test_vendor_match_after_normalization():
    # Whitespace + case differences only; both normalize identically.
    r = ENGINE.match(_invoice(), _po(vendor="mekong  supplies  co.,  ltd."), _grni(), _pard())
    assert MatchCode.VENDOR_MISMATCH not in _codes(r)


def test_currency_normalized_lowercase():
    r = ENGINE.match(_invoice(currency="usd"), _po(), _grni(), _pard())
    assert MatchCode.CURRENCY_MISMATCH not in _codes(r)


def test_currency_mismatch_invoice_vs_po_when_po_currency_set():
    r = ENGINE.match(_invoice(currency="USD"), _po(currency="KHR"), _grni(), _pard())
    f = [x for x in r.failures if x.code is MatchCode.CURRENCY_MISMATCH]
    assert f and any("vs PO" in x.location for x in f)


def test_currency_mismatch_invoice_vs_pard_when_pard_currency_set():
    r = ENGINE.match(_invoice(currency="USD"), _po(), _grni(), _pard(currency="KHR"))
    f = [x for x in r.failures if x.code is MatchCode.CURRENCY_MISMATCH]
    assert f and any("vs PARD" in x.location for x in f)


def test_currency_mismatch_both_po_and_pard():
    r = ENGINE.match(_invoice(currency="USD"), _po(currency="KHR"), _grni(), _pard(currency="KHR"))
    f = [x for x in r.failures if x.code is MatchCode.CURRENCY_MISMATCH]
    assert len(f) == 2


def test_currency_check_skipped_when_po_currency_absent():
    r = ENGINE.match(_invoice(currency="USD"), _po(currency=None), _grni(), _pard())
    assert MatchCode.CURRENCY_MISMATCH not in _codes(r)


def test_currency_check_skipped_when_pard_currency_absent():
    r = ENGINE.match(_invoice(currency="USD"), _po(), _grni(), _pard(currency=None))
    assert MatchCode.CURRENCY_MISMATCH not in _codes(r)


def test_currency_check_normalizes_before_compare():
    r = ENGINE.match(_invoice(currency="usd"), _po(currency="USD"), _grni(), _pard())
    assert MatchCode.CURRENCY_MISMATCH not in _codes(r)


# --- Line checks -----------------------------------------------------------


def test_happy_path_match():
    r = ENGINE.match(_invoice(), _po(), _grni(), _pard())
    assert r.outcome is Outcome.MATCH
    assert r.score == 1.0
    assert r.failures == ()


def test_no_matching_po_line():
    inv = _invoice(lines=(_line(1, "Mystery Item", "1", "10.00", "10.00"),))
    r = ENGINE.match(inv, _po(), _grni(), _pard())
    assert MatchCode.NO_MATCHING_PO_LINE in _codes(r)


def test_no_matching_grni_line():
    inv = _invoice(lines=(_line(1, "Mystery Item", "1", "10.00", "10.00"),))
    r = ENGINE.match(inv, _po(), _grni(), _pard())
    assert MatchCode.NO_MATCHING_GRNI_LINE in _codes(r)


def test_qty_mismatch_beyond_tolerance():
    po = _po(lines=(_line(1, "Office Chair", "9", "45.00"), _line(2, "Desk Lamp", "20", "12.50"), _line(3, "Whiteboard", "5", "60.00")))
    r = ENGINE.match(_invoice(), po, _grni(), _pard())
    assert MatchCode.QTY_MISMATCH in _codes(r)


def test_qty_mismatch_within_tolerance():
    r = ENGINE.match(_invoice(), _po(), _grni(), _pard())  # 10 vs 10, exact
    assert MatchCode.QTY_MISMATCH not in _codes(r)


def test_unit_price_mismatch_absolute():
    # $45.00 vs $45.50: abs 0.50 > 0.01 AND rel 1.1% > 0.1% -> mismatch.
    po = _po(lines=(_line(1, "Office Chair", "10", "45.50"), _line(2, "Desk Lamp", "20", "12.50"), _line(3, "Whiteboard", "5", "60.00")))
    r = ENGINE.match(_invoice(), po, _grni(), _pard())
    assert MatchCode.UNIT_PRICE_MISMATCH in _codes(r)


def test_unit_price_mismatch_within_absolute():
    # $45.00 vs $45.005: abs 0.005 <= 0.01 -> within absolute tolerance.
    po = _po(lines=(_line(1, "Office Chair", "10", "45.005"), _line(2, "Desk Lamp", "20", "12.50"), _line(3, "Whiteboard", "5", "60.00")))
    r = ENGINE.match(_invoice(), po, _grni(), _pard())
    assert MatchCode.UNIT_PRICE_MISMATCH not in _codes(r)


def test_unit_price_mismatch_within_relative():
    # $10,000.00 vs $10,001.00: abs 1.00 > 0.01 but rel 0.01% <= 0.1% -> no failure.
    inv = _invoice(lines=(_line(1, "Server", "1", "10000.00", "10000.00"),))
    po = _po(lines=(_line(1, "Server", "1", "10001.00"),))
    r = ENGINE.match(inv, po, _grni(lines=(_line(1, "Server", "1"),)), _pard(amount="10000.00"))
    assert MatchCode.UNIT_PRICE_MISMATCH not in _codes(r)


def test_line_amount_mismatch():
    # Invoice line amount 500.00 disagrees with PO-implied 10*45.00=450.00.
    inv = _invoice(lines=(_line(1, "Office Chair", "10", "45.00", "500.00"),))
    po = _po(lines=(_line(1, "Office Chair", "10", "45.00"),))
    r = ENGINE.match(inv, po, _grni(lines=(_line(1, "Office Chair", "10"),)), _pard(amount="500.00"))
    assert MatchCode.LINE_AMOUNT_MISMATCH in _codes(r)


# --- PARD ------------------------------------------------------------------


def test_pard_amount_mismatch():
    r = ENGINE.match(_invoice(), _po(), _grni(), _pard(amount="999.50"))
    f = [x for x in r.failures if x.code is MatchCode.PARD_AMOUNT_MISMATCH]
    assert f and f[0].severity is Severity.BLOCKER


def test_pard_amount_within_tolerance():
    r = ENGINE.match(_invoice(), _po(), _grni(), _pard(amount="1100.01"))
    assert MatchCode.PARD_AMOUNT_MISMATCH not in _codes(r)


# --- Dates -----------------------------------------------------------------


def test_date_out_of_order():
    r = ENGINE.match(_invoice(), _po(), _grni(), _pard(pard_date=date(2026, 8, 10)))
    f = [x for x in r.failures if x.code is MatchCode.DATE_OUT_OF_ORDER]
    assert f and f[0].severity is Severity.INFO


def test_date_order_ok():
    r = ENGINE.match(_invoice(), _po(), _grni(), _pard(pard_date=date(2026, 8, 25)))
    assert MatchCode.DATE_OUT_OF_ORDER not in _codes(r)


# --- Outcome logic ---------------------------------------------------------


def test_outcome_match_requires_zero_failures():
    r = ENGINE.match(_invoice(), _po(), _grni(), _pard())
    assert r.outcome is Outcome.MATCH and r.failures == ()


def test_outcome_discrepancy_with_warning_only():
    r = ENGINE.match(_invoice(), _po(vendor="Other Vendor Co."), _grni(), _pard())
    assert r.outcome is Outcome.DISCREPANCY
    assert all(f.severity is not Severity.BLOCKER for f in r.failures)


def test_outcome_discrepancy_with_blocker():
    r = ENGINE.match(_invoice(), _po(), _grni(), _pard(amount="999.50"))
    assert r.outcome is Outcome.DISCREPANCY
    assert r.has_blocker


def test_outcome_pending_info_when_missing():
    r = ENGINE.match(_invoice(), None, _grni(), _pard())
    assert r.outcome is Outcome.PENDING_INFO
    assert r.is_pending


# --- Scoring ---------------------------------------------------------------


def test_score_is_bounded_zero_to_one():
    for r in (
        ENGINE.match(_invoice(), _po(), _grni(), _pard()),
        ENGINE.match(_invoice(), _po(vendor="X"), _grni(), _pard(amount="1.00")),
        ENGINE.match(_invoice(), None, None, None),
    ):
        assert 0.0 <= r.score <= 1.0


def test_score_decreases_with_failures():
    clean = ENGINE.match(_invoice(), _po(), _grni(), _pard())
    dirty = ENGINE.match(_invoice(), _po(vendor="X"), _grni(), _pard(amount="1.00"))
    assert dirty.score < clean.score


def test_score_exact_for_known_case():
    r = ENGINE.match(_invoice(), _po(vendor="Other Vendor Co."), _grni(), _pard())
    assert r.score == 0.7  # 1.0 - 0.3 (VENDOR_MISMATCH)


# --- Ordering & determinism ------------------------------------------------


def test_failures_are_ordered_by_severity_then_code_then_location():
    r = ENGINE.match(
        _invoice(vendor="A Corp"),
        _po(vendor="B Corp"),
        _grni(),
        _pard(amount="999.50", pard_date=date(2026, 8, 10)),
    )
    assert _codes(r) == [
        MatchCode.PARD_AMOUNT_MISMATCH,  # BLOCKER
        MatchCode.VENDOR_MISMATCH,  # WARNING
        MatchCode.DATE_OUT_OF_ORDER,  # INFO
    ]


def test_match_deterministic():
    a = ENGINE.match(_invoice(), _po(vendor="X"), _grni(), _pard(amount="1.00"))
    b = ENGINE.match(_invoice(), _po(vendor="X"), _grni(), _pard(amount="1.00"))
    assert a == b
    assert [f.code for f in a.failures] == [f.code for f in b.failures]


# --- Known normalization gap (P0.3) ----------------------------------------


def test_mixed_case_ocr_suffix_not_stripped():
    # "/Hni" is mixed-case; normalize_text does NOT strip it (D-018/D-023).
    # The vendor names therefore differ and VENDOR_MISMATCH is emitted.
    r = ENGINE.match(_invoice(), _po(vendor="Mekong Supplies Co., Ltd./Hni"), _grni(), _pard())
    assert MatchCode.VENDOR_MISMATCH in _codes(r)
