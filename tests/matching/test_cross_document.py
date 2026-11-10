"""PROD-B4 cross-document checks (D-113): tolerances, partial billing, tax vs
PO rate, PO reference, receipt after invoice, close item names."""

from datetime import date
from decimal import Decimal as D

from apmatch.matching.engine import MatchingEngine
from apmatch.matching.result import MatchCode, Outcome
from apmatch.schema.documents import GRNI, Invoice, LineItem, PaymentAdvice, PurchaseOrder

ENGINE = MatchingEngine()


def _l(no, desc, qty, price=None):
    q, p = D(qty), (D(price) if price is not None else None)
    return LineItem(no, desc, q, p, (q * p).quantize(D("0.01")) if p is not None else None)


def _case(inv_lines, po_lines, grn_lines, *, tax="100.00", po_total=None, po_ref="PO-1",
          inv_date=date(2026, 8, 20), grn_date=date(2026, 8, 18), currency="USD"):
    sub = sum((li.amount for li in inv_lines), D("0"))
    total = sub + D(tax)
    inv = Invoice("INV-1", "Mekong Supplies Co., Ltd.", inv_date, currency, sub, D(tax), total,
                  tuple(inv_lines), po_number=po_ref)
    po_sum = sum((li.amount for li in po_lines), D("0"))
    po = PurchaseOrder("PO-1", "Mekong Supplies Co., Ltd.", date(2026, 8, 15),
                       D(po_total) if po_total else po_sum * D("1.10"), tuple(po_lines), currency)
    grn = GRNI("GRN-1", "Mekong Supplies Co., Ltd.", grn_date, tuple(grn_lines))
    pard = PaymentAdvice("PARD-1", "INV-1", total, date(2026, 8, 25), None, currency)
    return ENGINE.match(inv, po, grn, pard)


def _codes(r):
    return {f.code for f in r.failures}


CHAIR = ("Office Chair", "10", "45.00")
LAMP = ("Desk Lamp", "20", "12.50")


def _std(**kw):
    inv = [_l(1, *CHAIR), _l(2, *LAMP)]
    return _case(inv, [_l(1, *CHAIR), _l(2, *LAMP)], [_l(1, "Office Chair", "10"), _l(2, "Desk Lamp", "20")],
                 tax="70.00", **kw)


def test_clean_case_matches():
    r = _std()
    assert r.outcome is Outcome.MATCH, r.failures


def test_partial_billing_against_po_is_fine_when_it_equals_receipt():
    inv = [_l(1, "Office Chair", "8", "45.00")]
    r = _case(inv, [_l(1, *CHAIR)], [_l(1, "Office Chair", "8")], tax="36.00", po_total="495.00")
    assert MatchCode.QTY_MISMATCH not in _codes(r)
    assert MatchCode.LINE_AMOUNT_MISMATCH not in _codes(r)


def test_over_billing_against_po_is_flagged():
    inv = [_l(1, "Office Chair", "12", "45.00")]
    r = _case(inv, [_l(1, *CHAIR)], [_l(1, "Office Chair", "12")], tax="54.00", po_total="495.00")
    assert MatchCode.QTY_MISMATCH in _codes(r)


def test_billing_more_than_received_is_flagged():
    inv = [_l(1, "Office Chair", "8", "45.00")]
    r = _case(inv, [_l(1, *CHAIR)], [_l(1, "Office Chair", "6")], tax="36.00", po_total="495.00")
    assert MatchCode.QTY_MISMATCH in _codes(r)


def test_tax_rate_differs_from_po_rate():
    # PO implies 10%; invoice charges 9% (63.00 instead of 70.00).
    r = _case(
        [_l(1, *CHAIR), _l(2, *LAMP)], [_l(1, *CHAIR), _l(2, *LAMP)],
        [_l(1, "Office Chair", "10"), _l(2, "Desk Lamp", "20")], tax="63.00")
    assert MatchCode.TAX_MISMATCH in _codes(r)


def test_tax_rounding_by_a_cent_is_fine():
    r = _case([_l(1, *CHAIR), _l(2, *LAMP)], [_l(1, *CHAIR), _l(2, *LAMP)],
              [_l(1, "Office Chair", "10"), _l(2, "Desk Lamp", "20")], tax="70.01")
    assert MatchCode.TAX_MISMATCH not in _codes(r)


def test_tax_check_skipped_when_po_total_excludes_tax():
    r = _case([_l(1, *CHAIR), _l(2, *LAMP)], [_l(1, *CHAIR), _l(2, *LAMP)],
              [_l(1, "Office Chair", "10"), _l(2, "Desk Lamp", "20")], tax="70.00", po_total="700.00")
    assert MatchCode.TAX_MISMATCH not in _codes(r)


def test_khr_tax_tolerance_is_whole_riel():
    inv = [_l(1, "Cement", "100", "35000")]
    po = [_l(1, "Cement", "100", "35000")]
    grn = [_l(1, "Cement", "100")]
    ok = _case(inv, po, grn, tax="350050", currency="KHR")
    bad = _case(inv, po, grn, tax="352500", currency="KHR")
    assert MatchCode.TAX_MISMATCH not in _codes(ok)
    assert MatchCode.TAX_MISMATCH in _codes(bad)


def test_invoice_without_po_reference_goes_to_review():
    r = _std(po_ref=None)
    assert MatchCode.PO_REFERENCE_MISMATCH in _codes(r)
    r2 = _std(po_ref="PO-9")
    assert MatchCode.PO_REFERENCE_MISMATCH in _codes(r2)
    r3 = _std(po_ref="po 1")  # same reference, different punctuation/case
    assert MatchCode.PO_REFERENCE_MISMATCH not in _codes(r3)


def test_goods_received_after_invoice_goes_to_review():
    r = _std(grn_date=date(2026, 8, 22))
    assert MatchCode.RECEIVED_AFTER_INVOICE in _codes(r)


def test_close_names_match_only_when_numbers_agree():
    inv = [_l(1, "UPS1000VA -600W -Line-interactive", "4", "98.75"),
           _l(2, "Belt, serpentine", "1", "70.00"),
           _l(3, "PLA+ 3D printer filmaent", "2", "20.00")]
    po = [_l(1, "UPS 1000VA", "4", "98.75"), _l(2, "Serpentine belt", "1", "70.00"),
          _l(3, "PLA+ 3D printer filament", "2", "20.00")]
    grn = [_l(1, "UPS 1000VA", "4"), _l(2, "Serpentine belt", "1"), _l(3, "PLA+ 3D printer filament", "2")]
    sub = sum((li.amount for li in inv), D("0"))
    r = _case(inv, po, grn, tax=str((sub * D("0.10")).quantize(D("0.01"))))
    assert r.outcome is Outcome.MATCH, r.failures

    # Same close name, but a different price: not the same line.
    r2 = _case([_l(1, "Office Chair Mat", "10", "60.00")], [_l(1, *CHAIR)],
               [_l(1, "Office Chair", "10")], tax="60.00")
    assert MatchCode.NO_MATCHING_PO_LINE in _codes(r2)
