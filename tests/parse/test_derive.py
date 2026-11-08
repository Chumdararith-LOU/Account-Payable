"""Derivation policy: fill implicit values, never override explicit ones."""

from datetime import date
from decimal import Decimal as D

from apmatch.parse.derive import derive, derive_invoice, derive_line, derive_po
from apmatch.schema.documents import GRNI, Invoice, LineItem, PurchaseOrder


def _line(q=None, p=None, a=None, no=1):
    return LineItem(line_no=no, description="x", quantity=q, unit_price=p, amount=a)


def test_derive_line_fills_exactly_one_missing_value():
    assert derive_line(_line(D("2"), D("10.5"), None)).amount == D("21.00")
    assert derive_line(_line(D("4"), None, D("10.00"))).unit_price == D("2.5000")
    assert derive_line(_line(None, D("2.50"), D("10.00"))).quantity == D("4.0000")


def test_derive_line_leaves_complete_or_underdetermined_lines_alone():
    full = _line(D("2"), D("10"), D("99"))  # inconsistent, but explicit: keep it
    assert derive_line(full) == full
    two_missing = _line(D("2"), None, None)
    assert derive_line(two_missing) == two_missing
    zero_qty = _line(D("0"), None, D("5"))
    assert derive_line(zero_qty) == zero_qty


def test_derive_line_quantity_must_reproduce_amount():
    # 10.00 / 3.00 = 3.3333 -> 3.3333 * 3 = 9.9999 -> 10.00 within a cent: accepted
    assert derive_line(_line(None, D("3.00"), D("10.00"))).quantity == D("3.3333")


def _inv(**kw):
    base = dict(
        invoice_number="INV-1", vendor_name="V", invoice_date=date(2026, 1, 1), currency="USD",
        subtotal=None, tax_amount=None, total=None,
        line_items=(_line(D("2"), D("10"), None, 1), _line(D("1"), D("5"), D("5.00"), 2)),
    )
    base.update(kw)
    return Invoice(**base)


def test_derive_invoice_header():
    inv = derive_invoice(_inv(total=D("27.50")))
    assert inv.line_items[0].amount == D("20.00")
    assert inv.subtotal == D("25.00")
    assert inv.tax_amount == D("2.50")
    assert inv.total == D("27.50")


def test_derive_invoice_total_from_subtotal_and_tax():
    inv = derive_invoice(_inv(tax_amount=D("0.00")))
    assert inv.total == D("25.00")


def test_derive_invoice_keeps_explicit_values():
    inv = derive_invoice(_inv(subtotal=D("30.00"), tax_amount=D("1.00"), total=D("31.00")))
    assert (inv.subtotal, inv.tax_amount, inv.total) == (D("30.00"), D("1.00"), D("31.00"))


def test_derive_invoice_with_discount():
    inv = derive_invoice(_inv(total=D("24.00"), discount_amount=D("2.00")))
    # tax = total - subtotal + discount = 24 - 25 + 2
    assert inv.tax_amount == D("1.00")


def test_derive_po_total_and_passthrough():
    po = PurchaseOrder(
        po_number="PO-1", vendor_name="V", po_date=date(2026, 1, 1), total=None,
        line_items=(_line(D("2"), D("10"), None),),
    )
    assert derive_po(po).total == D("20.00")
    grni = GRNI(grn_number="G-1", vendor_name="V", grni_date=date(2026, 1, 1), line_items=())
    assert derive(grni) is grni
    assert derive(None) is None
