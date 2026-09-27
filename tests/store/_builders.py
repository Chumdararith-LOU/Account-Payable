"""Document builders for the store round-trip tests.

Defaults produce valid P1-06 documents so a test that does not care about a
field can omit it. Money arguments are accepted as strings (or Decimal) and
coerced to Decimal here, at the test boundary — the repositories themselves
never coerce.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from apmatch.schema.documents import GRNI, Invoice, LineItem, PaymentAdvice, PurchaseOrder


def _dec(value: str | Decimal) -> Decimal:
    """Coerce a string/Decimal money value to Decimal (required fields)."""
    return value if isinstance(value, Decimal) else Decimal(value)


def _dec_opt(value: str | Decimal | None) -> Decimal | None:
    """Coerce a string/Decimal/None money value to Decimal (optional fields)."""
    return None if value is None else _dec(value)


def mk_line(
    line_no: int,
    description: str,
    qty: str | Decimal = "10.0",
    unit_price: str | Decimal | None = "45.00",
    amount: str | Decimal | None = "450.00",
    unit_of_measure: str | None = None,
) -> LineItem:
    return LineItem(
        line_no=line_no,
        description=description,
        quantity=_dec(qty),
        unit_price=_dec_opt(unit_price),
        amount=_dec_opt(amount),
        unit_of_measure=unit_of_measure,
    )


def mk_invoice(
    invoice_number="INV-001",
    vendor_name="Acme Corp",
    invoice_date=None,
    currency="USD",
    subtotal="450.00",
    tax_amount="45.00",
    total="495.00",
    line_items=None,
    po_number=None,
    grn_number=None,
    vendor_tax_id=None,
    discount_amount=None,
    source_file=None,
    tax_rate=None,
    discount_rate=None,
) -> Invoice:
    if invoice_date is None:
        invoice_date = date(2026, 1, 15)
    if line_items is None:
        line_items = (mk_line(1, "Widget"),)
    return Invoice(
        invoice_number=invoice_number,
        vendor_name=vendor_name,
        invoice_date=invoice_date,
        currency=currency,
        subtotal=_dec(subtotal),
        tax_amount=_dec(tax_amount),
        total=_dec(total),
        line_items=line_items,
        po_number=po_number,
        grn_number=grn_number,
        vendor_tax_id=vendor_tax_id,
        discount_amount=_dec_opt(discount_amount),
        source_file=source_file,
        tax_rate=_dec_opt(tax_rate),
        discount_rate=_dec_opt(discount_rate),
    )


def mk_po(
    po_number="PO-001",
    vendor_name="Acme Corp",
    po_date=None,
    total="495.00",
    line_items=None,
    currency="USD",
) -> PurchaseOrder:
    if po_date is None:
        po_date = date(2026, 1, 10)
    if line_items is None:
        line_items = (mk_line(1, "Widget"),)
    return PurchaseOrder(
        po_number=po_number,
        vendor_name=vendor_name,
        po_date=po_date,
        total=_dec(total),
        line_items=line_items,
        currency=currency,
    )


def mk_grni(
    grn_number="GRN-001",
    vendor_name="Acme Corp",
    grni_date=None,
    line_items=None,
) -> GRNI:
    if grni_date is None:
        grni_date = date(2026, 1, 12)
    if line_items is None:
        # GRNI lines carry quantity only — no price/amount.
        line_items = (mk_line(1, "Widget", unit_price=None, amount=None),)
    return GRNI(
        grn_number=grn_number,
        vendor_name=vendor_name,
        grni_date=grni_date,
        line_items=line_items,
    )


def mk_pard(
    pard_number="PARD-001",
    invoice_number="INV-001",
    amount="495.00",
    payment_date=None,
    reference=None,
    currency="USD",
) -> PaymentAdvice:
    if payment_date is None:
        payment_date = date(2026, 1, 20)
    return PaymentAdvice(
        pard_number=pard_number,
        invoice_number=invoice_number,
        amount=_dec(amount),
        payment_date=payment_date,
        reference=reference,
        currency=currency,
    )
