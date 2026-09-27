"""SQLAlchemy 2.x ORM models mirroring the P1-06 document dataclasses.

The schema matches ``apmatch.schema.documents`` exactly — no invented columns.
Money and quantity columns are ``Numeric(18, 4)``; Float/REAL/Double are
forbidden (the SQLite prototype used REAL, which silently loses cents on large
values). Line tables use per-table columns (not a mixin) for clarity; each line
table's primary key is the composite (document number, line_no), matching the
dataclass semantics where ``line_no`` is unique within a document.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Money / quantity precision. 18 digits total, 4 after the point.
MONEY = Numeric(18, 4)


class Base(DeclarativeBase):
    pass


metadata = Base.metadata


class InvoiceHeader(Base):
    __tablename__ = "invoice_headers"

    invoice_number: Mapped[str] = mapped_column(String(64), primary_key=True)
    vendor_name: Mapped[str] = mapped_column(String(255))
    invoice_date: Mapped[date] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(8))
    subtotal: Mapped[Decimal] = mapped_column(MONEY)
    tax_amount: Mapped[Decimal] = mapped_column(MONEY)
    total: Mapped[Decimal] = mapped_column(MONEY)
    po_number: Mapped[str | None] = mapped_column(String(64))
    grn_number: Mapped[str | None] = mapped_column(String(64))
    vendor_tax_id: Mapped[str | None] = mapped_column(String(64))
    discount_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    source_file: Mapped[str | None] = mapped_column(String(255))
    tax_rate: Mapped[Decimal | None] = mapped_column(MONEY)
    discount_rate: Mapped[Decimal | None] = mapped_column(MONEY)


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    invoice_number: Mapped[str] = mapped_column(
        String(64), ForeignKey("invoice_headers.invoice_number"), primary_key=True
    )
    line_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    description: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[Decimal] = mapped_column(MONEY)
    unit_price: Mapped[Decimal | None] = mapped_column(MONEY)
    amount: Mapped[Decimal | None] = mapped_column(MONEY)
    unit_of_measure: Mapped[str | None] = mapped_column(String(16))


class PoHeader(Base):
    __tablename__ = "po_headers"

    po_number: Mapped[str] = mapped_column(String(64), primary_key=True)
    vendor_name: Mapped[str] = mapped_column(String(255))
    po_date: Mapped[date] = mapped_column(Date)
    total: Mapped[Decimal] = mapped_column(MONEY)
    currency: Mapped[str | None] = mapped_column(String(8))


class PoLine(Base):
    __tablename__ = "po_lines"

    po_number: Mapped[str] = mapped_column(
        String(64), ForeignKey("po_headers.po_number"), primary_key=True
    )
    line_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    description: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[Decimal] = mapped_column(MONEY)
    unit_price: Mapped[Decimal | None] = mapped_column(MONEY)
    amount: Mapped[Decimal | None] = mapped_column(MONEY)
    unit_of_measure: Mapped[str | None] = mapped_column(String(16))


class GrniHeader(Base):
    __tablename__ = "grni_headers"

    grn_number: Mapped[str] = mapped_column(String(64), primary_key=True)
    vendor_name: Mapped[str] = mapped_column(String(255))
    grni_date: Mapped[date] = mapped_column(Date)


class GrniLine(Base):
    __tablename__ = "grni_lines"

    grn_number: Mapped[str] = mapped_column(
        String(64), ForeignKey("grni_headers.grn_number"), primary_key=True
    )
    line_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    description: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[Decimal] = mapped_column(MONEY)
    # GRNI records quantities only; unit_price/amount are part of the shared
    # LineItem dataclass (optional) and are NULL for GRNI rows.
    unit_price: Mapped[Decimal | None] = mapped_column(MONEY)
    amount: Mapped[Decimal | None] = mapped_column(MONEY)
    unit_of_measure: Mapped[str | None] = mapped_column(String(16))


class Pard(Base):
    __tablename__ = "pard"

    pard_number: Mapped[str] = mapped_column(String(64), primary_key=True)
    invoice_number: Mapped[str] = mapped_column(
        String(64), ForeignKey("invoice_headers.invoice_number")
    )
    amount: Mapped[Decimal] = mapped_column(MONEY)
    payment_date: Mapped[date] = mapped_column(Date)
    reference: Mapped[str | None] = mapped_column(String(64))
    currency: Mapped[str | None] = mapped_column(String(8))
