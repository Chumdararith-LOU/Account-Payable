"""Deterministic derivation of implicit values, shared by every extractor.

Extends the P1-10c-fix / D-044 policy to all documents and to line level:
explicit source values are always preserved; a value is derived only when the
document omits it AND the inputs needed to compute it are present.

Line level (invoice + PO lines): if exactly one of quantity / unit_price /
amount is missing, compute it from the other two. Quantity is only derived
when the result is consistent (qty * price reproduces the amount to the
cent), so a derivation never invents a value the document contradicts.

Header level:
- invoice subtotal = sum of line amounts (only when every line has one)
- invoice tax      = total - subtotal + discount
- invoice total    = subtotal - discount + tax
- PO total         = sum of line amounts (only when every line has one)

Pure, no I/O. Applied in ``apmatch.api.pipeline`` to whatever the extraction
backend (VLM or OCR heuristics) returned.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal, InvalidOperation

from apmatch.schema.coercion import to_money, to_qty, to_unit_price
from apmatch.schema.documents import GRNI, Invoice, LineItem, PaymentAdvice, PurchaseOrder

_CENT = Decimal("0.01")


def derive_line(line: LineItem) -> LineItem:
    """Fill the one missing value of (quantity, unit_price, amount), if any."""
    q, p, a = line.quantity, line.unit_price, line.amount
    missing = [name for name, v in (("q", q), ("p", p), ("a", a)) if v is None]
    if len(missing) != 1:
        return line
    try:
        if missing == ["a"]:
            return replace(line, amount=to_money(q * p))
        if missing == ["p"] and q != 0:
            return replace(line, unit_price=to_unit_price(a / q))
        if missing == ["q"] and p != 0:
            qty = to_qty(a / p)
            if abs(to_money(qty * p) - a) <= _CENT:
                return replace(line, quantity=qty)
    except (InvalidOperation, ArithmeticError):
        return line
    return line


def _all_amounts(lines: tuple[LineItem, ...]) -> list[Decimal] | None:
    amounts = [li.amount for li in lines]
    if not amounts or any(a is None for a in amounts):
        return None
    return amounts


def derive_invoice(inv: Invoice) -> Invoice:
    lines = tuple(derive_line(li) for li in inv.line_items)
    subtotal, tax, total = inv.subtotal, inv.tax_amount, inv.total
    discount = inv.discount_amount if inv.discount_amount is not None else Decimal("0")

    amounts = _all_amounts(lines)
    if subtotal is None and amounts is not None:
        subtotal = to_money(sum(amounts, Decimal("0")))
    if tax is None and total is not None and subtotal is not None:
        tax = to_money(total - subtotal + discount)
    if total is None and subtotal is not None and tax is not None:
        total = to_money(subtotal - discount + tax)
    return replace(inv, line_items=lines, subtotal=subtotal, tax_amount=tax, total=total)


def derive_po(po: PurchaseOrder) -> PurchaseOrder:
    lines = tuple(derive_line(li) for li in po.line_items)
    total = po.total
    amounts = _all_amounts(lines)
    if total is None and amounts is not None:
        total = to_money(sum(amounts, Decimal("0")))
    return replace(po, line_items=lines, total=total)


def derive(doc):
    """Apply the derivation policy to any pipeline document (None passes through)."""
    if isinstance(doc, Invoice):
        return derive_invoice(doc)
    if isinstance(doc, PurchaseOrder):
        return derive_po(doc)
    if isinstance(doc, (GRNI, PaymentAdvice)) or doc is None:
        return doc
    return doc
