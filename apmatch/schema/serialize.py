"""Rebuild schema dataclasses from their canonical JSON form.

The inverse of ``apmatch.audit.hashing.canonical_documents``: Decimals come
back from strings, dates from ISO strings, tuples from lists. Used by the
extraction cache (``apmatch.api.pipeline``) and by ``scripts/rematch_report.py``,
which re-runs validation + matching + routing on documents stored in a batch
report without touching OCR or the VLM.

Pure, deterministic, no I/O. Money/quantity values go through the same
coercion boundary as every other path (``to_money`` / ``to_qty`` /
``to_unit_price``), so a canonical dict can never smuggle a float in.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from apmatch.schema.coercion import to_money, to_qty, to_unit_price
from apmatch.schema.documents import GRNI, Invoice, LineItem, PaymentAdvice, PurchaseOrder

# Keys used by canonical_documents() for the four pipeline documents.
DOC_KEYS = ("invoice", "po", "grni", "pard")


def _money(v) -> Decimal | None:
    return None if v is None else to_money(str(v))


def _qty(v) -> Decimal | None:
    return None if v is None else to_qty(str(v))


def _price(v) -> Decimal | None:
    return None if v is None else to_unit_price(str(v))


def _date(v) -> date | None:
    return None if not v else date.fromisoformat(str(v))


def _dec(v) -> Decimal | None:
    return None if v is None else Decimal(str(v))


def _lines(items) -> tuple[LineItem, ...]:
    out = []
    for i, li in enumerate(items or [], start=1):
        out.append(
            LineItem(
                line_no=int(li.get("line_no") or i),
                description=li.get("description") or "",
                quantity=_qty(li.get("quantity")),
                unit_price=_price(li.get("unit_price")),
                amount=_money(li.get("amount")),
                unit_of_measure=li.get("unit_of_measure"),
            )
        )
    return tuple(out)


def invoice_from_dict(d: dict) -> Invoice:
    return Invoice(
        invoice_number=d.get("invoice_number"),
        vendor_name=d.get("vendor_name"),
        invoice_date=_date(d.get("invoice_date")),
        currency=d.get("currency"),
        subtotal=_money(d.get("subtotal")),
        tax_amount=_money(d.get("tax_amount")),
        total=_money(d.get("total")),
        line_items=_lines(d.get("line_items")),
        po_number=d.get("po_number"),
        grn_number=d.get("grn_number"),
        vendor_tax_id=d.get("vendor_tax_id"),
        discount_amount=_money(d.get("discount_amount")),
        source_file=d.get("source_file"),
        tax_rate=_dec(d.get("tax_rate")),
        discount_rate=_dec(d.get("discount_rate")),
        duplicate_of_run_id=d.get("duplicate_of_run_id"),
    )


def po_from_dict(d: dict) -> PurchaseOrder:
    return PurchaseOrder(
        po_number=d.get("po_number"),
        vendor_name=d.get("vendor_name"),
        po_date=_date(d.get("po_date")),
        total=_money(d.get("total")),
        line_items=_lines(d.get("line_items")),
        currency=d.get("currency"),
    )


def grni_from_dict(d: dict) -> GRNI:
    return GRNI(
        grn_number=d.get("grn_number"),
        vendor_name=d.get("vendor_name"),
        grni_date=_date(d.get("grni_date")),
        line_items=_lines(d.get("line_items")),
    )


def pard_from_dict(d: dict) -> PaymentAdvice:
    return PaymentAdvice(
        pard_number=d.get("pard_number"),
        invoice_number=d.get("invoice_number"),
        amount=_money(d.get("amount")),
        payment_date=_date(d.get("payment_date")),
        reference=d.get("reference"),
        currency=d.get("currency"),
    )


_BUILDERS = {
    "invoice": invoice_from_dict,
    "po": po_from_dict,
    "grni": grni_from_dict,
    "pard": pard_from_dict,
}


def document_from_dict(key: str, d: dict | None):
    """Rebuild one document. ``key`` is one of DOC_KEYS; None stays None."""
    if d is None:
        return None
    return _BUILDERS[key](d)


def documents_from_canonical(docs: dict) -> tuple:
    """(invoice, po, grni, pard) from a canonical_documents() dict."""
    return tuple(document_from_dict(k, docs.get(k)) for k in DOC_KEYS)
