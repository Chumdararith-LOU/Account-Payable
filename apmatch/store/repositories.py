"""Thin repository layer over the P1-10a SQLAlchemy models.

This module is a thin persistence boundary with no business logic (no matching,
no validation, no scoring). Its sole responsibility is mapping the P1-06
document dataclasses to and from Postgres rows:

- Decimal <-> Numeric(18, 4)
- date <-> Date
- tuple[LineItem, ...] <-> list of line rows

Round-trip guarantee: ``load(session, save(session, x)) == x`` for every
document kind, with Decimal precision preserved exactly (no float coercion, no
str() round-trips). The dataclass already guarantees Decimal on the way in
(P1-06); this layer does not coerce.

Caller manages transactions (SQLAlchemy 2.x idiom). The repositories never
commit; they flush so that a subsequent ``load`` in the same transaction can
see the saved rows. The caller decides when to commit or roll back.

No ORM magic at the boundary: the public API takes and returns P1-06
dataclasses, never ORM instances. ORM instances never cross the boundary.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from apmatch.schema.documents import (
    GRNI,
    Invoice,
    LineItem,
    PaymentAdvice,
    PurchaseOrder,
)
from apmatch.store.models import (
    GrniHeader,
    GrniLine,
    InvoiceHeader,
    InvoiceLine,
    Pard,
    PoHeader,
    PoLine,
)


class DocumentKind(str, Enum):
    """The four document kinds the repository layer persists."""

    INVOICE = "invoice"
    PURCHASE_ORDER = "purchase_order"
    GRNI = "grni"
    PAYMENT_ADVICE = "payment_advice"


class DocumentNotFound(Exception):
    """Raised by ``load`` when no row matches the identifier.

    Carries the document kind and identifier so a reviewer or audit log can
    tell which document was missing and by what key. A bare ``KeyError`` does
    not carry enough context.
    """

    def __init__(self, kind: DocumentKind, identifier: str) -> None:
        self.kind = kind
        self.identifier = identifier
        super().__init__(f"{kind.value} not found: {identifier!r}")


def _line_to_orm_line(orm_cls, doc_number: str, line: LineItem):
    return orm_cls(
        **{orm_cls.__table__.c[0].name: doc_number},
        line_no=line.line_no,
        description=line.description,
        quantity=line.quantity,
        unit_price=line.unit_price,
        amount=line.amount,
        unit_of_measure=line.unit_of_measure,
    )


def _orm_line_to_line(row) -> LineItem:
    return LineItem(
        line_no=row.line_no,
        description=row.description,
        quantity=row.quantity,
        unit_price=row.unit_price,
        amount=row.amount,
        unit_of_measure=row.unit_of_measure,
    )


class InvoiceRepository:
    """save/load/exists/delete for :class:`Invoice`. No state; static methods."""

    @staticmethod
    def save(session: Session, invoice: Invoice) -> None:
        # Upsert: delete existing lines (FK children) then header, flush, then
        # insert fresh. delete-then-insert (not merge()) keeps line ordering
        # predictable and avoids identity-map surprises (D-033).
        for row in session.execute(
            select(InvoiceLine).where(InvoiceLine.invoice_number == invoice.invoice_number)
        ).scalars():
            session.delete(row)
        existing = session.get(InvoiceHeader, invoice.invoice_number)
        if existing is not None:
            session.delete(existing)
        session.flush()
        session.add(
            InvoiceHeader(
                invoice_number=invoice.invoice_number,
                vendor_name=invoice.vendor_name,
                invoice_date=invoice.invoice_date,
                currency=invoice.currency,
                subtotal=invoice.subtotal,
                tax_amount=invoice.tax_amount,
                total=invoice.total,
                po_number=invoice.po_number,
                grn_number=invoice.grn_number,
                vendor_tax_id=invoice.vendor_tax_id,
                discount_amount=invoice.discount_amount,
                source_file=invoice.source_file,
                tax_rate=invoice.tax_rate,
                discount_rate=invoice.discount_rate,
            )
        )
        for line in invoice.line_items:
            session.add(_line_to_orm_line(InvoiceLine, invoice.invoice_number, line))
        session.flush()

    @staticmethod
    def load(session: Session, invoice_number: str) -> Invoice:
        header = session.get(InvoiceHeader, invoice_number)
        if header is None:
            raise DocumentNotFound(DocumentKind.INVOICE, invoice_number)
        rows = session.execute(
            select(InvoiceLine)
            .where(InvoiceLine.invoice_number == invoice_number)
            .order_by(InvoiceLine.line_no)
        ).scalars().all()
        return Invoice(
            invoice_number=header.invoice_number,
            vendor_name=header.vendor_name,
            invoice_date=header.invoice_date,
            currency=header.currency,
            subtotal=header.subtotal,
            tax_amount=header.tax_amount,
            total=header.total,
            line_items=tuple(_orm_line_to_line(r) for r in rows),
            po_number=header.po_number,
            grn_number=header.grn_number,
            vendor_tax_id=header.vendor_tax_id,
            discount_amount=header.discount_amount,
            source_file=header.source_file,
            tax_rate=header.tax_rate,
            discount_rate=header.discount_rate,
        )

    @staticmethod
    def exists(session: Session, invoice_number: str) -> bool:
        return session.get(InvoiceHeader, invoice_number) is not None

    @staticmethod
    def delete(session: Session, invoice_number: str) -> None:
        for row in session.execute(
            select(InvoiceLine).where(InvoiceLine.invoice_number == invoice_number)
        ).scalars():
            session.delete(row)
        existing = session.get(InvoiceHeader, invoice_number)
        if existing is not None:
            session.delete(existing)
        session.flush()


class PurchaseOrderRepository:
    """save/load/exists/delete for :class:`PurchaseOrder`."""

    @staticmethod
    def save(session: Session, po: PurchaseOrder) -> None:
        for row in session.execute(
            select(PoLine).where(PoLine.po_number == po.po_number)
        ).scalars():
            session.delete(row)
        existing = session.get(PoHeader, po.po_number)
        if existing is not None:
            session.delete(existing)
        session.flush()
        session.add(
            PoHeader(
                po_number=po.po_number,
                vendor_name=po.vendor_name,
                po_date=po.po_date,
                total=po.total,
                currency=po.currency,
            )
        )
        for line in po.line_items:
            session.add(_line_to_orm_line(PoLine, po.po_number, line))
        session.flush()

    @staticmethod
    def load(session: Session, po_number: str) -> PurchaseOrder:
        header = session.get(PoHeader, po_number)
        if header is None:
            raise DocumentNotFound(DocumentKind.PURCHASE_ORDER, po_number)
        rows = session.execute(
            select(PoLine).where(PoLine.po_number == po_number).order_by(PoLine.line_no)
        ).scalars().all()
        return PurchaseOrder(
            po_number=header.po_number,
            vendor_name=header.vendor_name,
            po_date=header.po_date,
            total=header.total,
            line_items=tuple(_orm_line_to_line(r) for r in rows),
            currency=header.currency,
        )

    @staticmethod
    def exists(session: Session, po_number: str) -> bool:
        return session.get(PoHeader, po_number) is not None

    @staticmethod
    def delete(session: Session, po_number: str) -> None:
        for row in session.execute(
            select(PoLine).where(PoLine.po_number == po_number)
        ).scalars():
            session.delete(row)
        existing = session.get(PoHeader, po_number)
        if existing is not None:
            session.delete(existing)
        session.flush()


class GRNIRepository:
    """save/load/exists/delete for :class:`GRNI` (quantity only)."""

    @staticmethod
    def save(session: Session, grni: GRNI) -> None:
        for row in session.execute(
            select(GrniLine).where(GrniLine.grn_number == grni.grn_number)
        ).scalars():
            session.delete(row)
        existing = session.get(GrniHeader, grni.grn_number)
        if existing is not None:
            session.delete(existing)
        session.flush()
        session.add(
            GrniHeader(
                grn_number=grni.grn_number,
                vendor_name=grni.vendor_name,
                grni_date=grni.grni_date,
            )
        )
        for line in grni.line_items:
            session.add(_line_to_orm_line(GrniLine, grni.grn_number, line))
        session.flush()

    @staticmethod
    def load(session: Session, grni_number: str) -> GRNI:
        header = session.get(GrniHeader, grni_number)
        if header is None:
            raise DocumentNotFound(DocumentKind.GRNI, grni_number)
        rows = session.execute(
            select(GrniLine)
            .where(GrniLine.grn_number == grni_number)
            .order_by(GrniLine.line_no)
        ).scalars().all()
        return GRNI(
            grn_number=header.grn_number,
            vendor_name=header.vendor_name,
            grni_date=header.grni_date,
            line_items=tuple(_orm_line_to_line(r) for r in rows),
        )

    @staticmethod
    def exists(session: Session, grni_number: str) -> bool:
        return session.get(GrniHeader, grni_number) is not None

    @staticmethod
    def delete(session: Session, grni_number: str) -> None:
        for row in session.execute(
            select(GrniLine).where(GrniLine.grn_number == grni_number)
        ).scalars():
            session.delete(row)
        existing = session.get(GrniHeader, grni_number)
        if existing is not None:
            session.delete(existing)
        session.flush()


class PaymentAdviceRepository:
    """save/load/exists/delete for :class:`PaymentAdvice` (single total, no lines)."""

    @staticmethod
    def save(session: Session, pard: PaymentAdvice) -> None:
        existing = session.get(Pard, pard.pard_number)
        if existing is not None:
            session.delete(existing)
        session.flush()
        session.add(
            Pard(
                pard_number=pard.pard_number,
                invoice_number=pard.invoice_number,
                amount=pard.amount,
                payment_date=pard.payment_date,
                reference=pard.reference,
                currency=pard.currency,
            )
        )
        session.flush()

    @staticmethod
    def load(session: Session, pard_ref: str) -> PaymentAdvice:
        row = session.get(Pard, pard_ref)
        if row is None:
            raise DocumentNotFound(DocumentKind.PAYMENT_ADVICE, pard_ref)
        return PaymentAdvice(
            pard_number=row.pard_number,
            invoice_number=row.invoice_number,
            amount=row.amount,
            payment_date=row.payment_date,
            reference=row.reference,
            currency=row.currency,
        )

    @staticmethod
    def exists(session: Session, pard_ref: str) -> bool:
        return session.get(Pard, pard_ref) is not None

    @staticmethod
    def delete(session: Session, pard_ref: str) -> None:
        row = session.get(Pard, pard_ref)
        if row is not None:
            session.delete(row)
            session.flush()
