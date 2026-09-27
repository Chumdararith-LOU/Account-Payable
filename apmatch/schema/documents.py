"""Canonical in-memory representation of AP documents.

Deterministic, no I/O, no ML. This is the contract that every downstream
module (validation, matching, remarks, audit) consumes. Every monetary field
is a ``decimal.Decimal``; all dataclasses are frozen.

The field sets mirror the legacy SQLite schema in ``database.py`` (the
ground truth from P1-06 Checkpoint A) extended with the richer contract
fields the matching engine needs. Columns present in the DB but not in the
original design are carried as optional fields (default ``None``):

- ``created_at`` — audit timestamp on PO/GRNI/INVOICE headers (DB TIMESTAMP).
- ``LineItem.unit_price`` / ``LineItem.amount`` are optional because the DB's
  ``GRNI_LINE`` stores only ``Item`` and ``Qty`` (no price, no amount); the
  shared ``LineItem`` must fit Invoice/PO (price+amount) and GRNI (qty only).

DB storage notes (ambiguities the Decimal contract fixes):
- Money is stored as ``REAL`` (float) in the DB; here it is always Decimal.
- Dates are stored as TEXT (e.g. ``15-Aug-2026``); here they are ``date``.
- Line-to-header linkage is stored as FK columns (``PO_ID``/``GRNI_ID``/
  ``INV_ID``) and is represented structurally by the nested ``line_items``
  tuple, not as a field. Line surrogate IDs (``*_LINE_ID``) are DB storage
  details and are not carried; ``line_no`` is a 1-based logical number.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

# Quantization constants.
MONEY_QUANTUM = Decimal("0.01")
UNIT_PRICE_QUANTUM = Decimal("0.0001")
QTY_QUANTUM = Decimal("0.0001")
ROUNDING = ROUND_HALF_UP

# Type aliases.
Money = Decimal  # always quantize(MONEY_QUANTUM)
UnitPrice = Decimal  # always quantize(UNIT_PRICE_QUANTUM)
Quantity = Decimal  # always quantize(QTY_QUANTUM)


@dataclass(frozen=True)
class LineItem:
    """One line on an invoice, PO, or GRNI.

    ``unit_price`` and ``amount`` are optional: GRNI lines carry quantity
    only (the DB has no price/amount for GRNI_LINE).
    """

    line_no: int
    description: str
    quantity: Quantity
    unit_price: UnitPrice | None = None
    amount: Money | None = None
    unit_of_measure: str | None = None


@dataclass(frozen=True)
class Invoice:
    """A vendor invoice (INVOICE_HEADER + INVOICE_LINE)."""

    invoice_number: str
    vendor_name: str
    invoice_date: date
    currency: str  # ISO 4217
    subtotal: Money
    tax_amount: Money
    total: Money
    line_items: tuple[LineItem, ...]
    po_number: str | None = None
    grn_number: str | None = None
    vendor_tax_id: str | None = None
    discount_amount: Money | None = None
    source_file: str | None = None
    created_at: datetime | None = None  # DB INVOICE_HEADER.created_at


@dataclass(frozen=True)
class PurchaseOrder:
    """A purchase order (PO_HEADER + PO_LINE)."""

    po_number: str
    vendor_name: str
    po_date: date
    total: Money
    line_items: tuple[LineItem, ...]
    created_at: datetime | None = None  # DB PO_HEADER.created_at


@dataclass(frozen=True)
class GRNI:
    """A goods-received note (GRNI_HEADER + GRNI_LINE). Quantity only."""

    grn_number: str
    vendor_name: str
    grni_date: date
    line_items: tuple[LineItem, ...]
    created_at: datetime | None = None  # DB GRNI_HEADER.created_at


@dataclass(frozen=True)
class PaymentAdvice:
    """A payment advice / remittance (PARD). Single total, no lines."""

    pard_number: str
    invoice_number: str  # DB PARD.INV_ID (FK to INVOICE_HEADER)
    amount: Money
    payment_date: date
    reference: str | None = None  # DB PARD.Ref
