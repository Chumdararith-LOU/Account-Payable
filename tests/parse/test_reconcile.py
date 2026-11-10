"""Case-level reconcile: currency fill and ambiguous-date resolution (D-114)."""

from datetime import date
from decimal import Decimal as D

from apmatch.parse.reconcile import fill_currency, reconcile, resolve_dates
from apmatch.schema.documents import GRNI, Invoice, PaymentAdvice, PurchaseOrder


def _docs(inv_date, po_date, grn_date, pay_date, inv_cur="USD", po_cur="USD", pard_cur="USD"):
    return {
        "invoice": Invoice("INV-1", "V", inv_date, inv_cur, D("1"), D("0"), D("1"), ()),
        "po": PurchaseOrder("PO-1", "V", po_date, D("1"), (), po_cur),
        "grni": GRNI("G-1", "V", grn_date, ()),
        "pard": PaymentAdvice("P-1", "INV-1", D("1"), pay_date, None, pard_cur),
    }


def test_currency_taken_from_po_then_pard_then_usd():
    assert fill_currency(_docs(None, None, None, None, inv_cur=None, po_cur="KHR"))["invoice"].currency == "KHR"
    assert fill_currency(_docs(None, None, None, None, inv_cur=None, po_cur=None, pard_cur="KHR"))[
        "invoice"].currency == "KHR"
    assert fill_currency(_docs(None, None, None, None, inv_cur=None, po_cur=None, pard_cur=None))[
        "invoice"].currency == "USD"
    stated = _docs(None, None, None, None, inv_cur="USD", po_cur="KHR")
    assert fill_currency(stated)["invoice"].currency == "USD"  # never overrides a stated currency


def test_us_dates_resolved_to_a_coherent_order():
    # Printed 04/09/2025 (inv), 04/08/2025 (po), 04/09/2025 (grn), 05/02/2025 (pay):
    # the extractor read the PO and GRN day-first; MM/DD is the coherent reading.
    docs = _docs(date(2025, 4, 9), date(2025, 8, 4), date(2025, 9, 4), date(2025, 5, 2))
    cands = {
        "invoice": [date(2025, 9, 4), date(2025, 4, 9)],
        "po": [date(2025, 8, 4), date(2025, 4, 8)],
        "grni": [date(2025, 9, 4), date(2025, 4, 9)],
        "pard": [date(2025, 2, 5), date(2025, 5, 2)],
    }
    out = resolve_dates(docs, cands)
    assert out["po"].po_date == date(2025, 4, 8)
    assert out["grni"].grni_date == date(2025, 4, 9)
    assert out["invoice"].invoice_date == date(2025, 4, 9)
    assert out["pard"].payment_date == date(2025, 5, 2)


def test_unambiguous_dates_are_never_changed():
    # Payment printed unambiguously BEFORE the invoice: a real problem, kept.
    docs = _docs(date(2025, 4, 20), date(2025, 4, 1), date(2025, 4, 10), date(2025, 4, 15))
    cands = {"invoice": [date(2025, 4, 20)], "po": [date(2025, 4, 1)],
             "grni": [date(2025, 4, 10)], "pard": [date(2025, 4, 15)]}
    assert resolve_dates(docs, cands) == docs
    assert reconcile(docs, None) == docs


def test_misread_unit_price_repaired_only_when_amount_agrees_with_po():
    from apmatch.schema.documents import LineItem

    def inv_with(price, amount):
        line = LineItem(1, "Stapler", D("17"), D(price), D(amount))
        return Invoice("INV-1", "V", None, "USD", D("1"), D("0"), D("1"), (line,))

    po = PurchaseOrder("PO-1", "V", None, D("1"), (LineItem(1, "Stapler", D("17"), D("13.80"), D("234.60")),))
    fixed = reconcile({"invoice": inv_with("12.80", "234.60"), "po": po, "grni": None, "pard": None})
    assert fixed["invoice"].line_items[0].unit_price == D("13.8000")
    # Price as on the PO but amount wrong: a real error, left for validation.
    kept = reconcile({"invoice": inv_with("13.80", "250.00"), "po": po, "grni": None, "pard": None})
    assert kept["invoice"].line_items[0].unit_price == D("13.80")
