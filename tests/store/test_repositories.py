"""Round-trip tests for the repository layer.

The core guarantee: ``load(session, save(session, x)) == x`` for every document
kind, with Decimal precision preserved exactly. These tests run against a real
Postgres (skipped if unreachable, via the conftest ``pg_engine`` fixture).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from apmatch.schema.documents import GRNI, Invoice, PaymentAdvice, PurchaseOrder
from apmatch.store.repositories import (
    DocumentKind,
    DocumentNotFound,
    GRNIRepository,
    InvoiceRepository,
    PaymentAdviceRepository,
    PurchaseOrderRepository,
)
from tests.store._builders import mk_grni, mk_invoice, mk_line, mk_pard, mk_po

# --- Round-trip: the core guarantee -----------------------------------------


def test_invoice_round_trip(pg_session):
    inv = mk_invoice(
        invoice_number="INV-RT-1",
        vendor_name="Acme Corp",
        currency="USD",
        subtotal="450.00",
        tax_amount="45.00",
        total="495.00",
        line_items=(
            mk_line(1, "Widget", qty="10.0", unit_price="45.00", amount="450.00", unit_of_measure="EA"),
            mk_line(2, "Gadget", qty="2.0", unit_price="100.00", amount="200.00", unit_of_measure="BOX"),
        ),
        po_number="PO-1",
        grn_number="GRN-1",
        vendor_tax_id="TAX-123",
        discount_amount="10.00",
        source_file="inv.pdf",
        tax_rate="0.10",
        discount_rate="0.02",
    )
    InvoiceRepository.save(pg_session, inv)
    loaded = InvoiceRepository.load(pg_session, inv.invoice_number)

    assert loaded == inv
    assert type(loaded) is Invoice
    assert loaded.invoice_number == inv.invoice_number
    assert loaded.vendor_name == inv.vendor_name
    assert loaded.invoice_date == inv.invoice_date
    assert loaded.currency == inv.currency
    assert loaded.subtotal == inv.subtotal
    assert loaded.tax_amount == inv.tax_amount
    assert loaded.total == inv.total
    assert loaded.po_number == inv.po_number
    assert loaded.grn_number == inv.grn_number
    assert loaded.vendor_tax_id == inv.vendor_tax_id
    assert loaded.discount_amount == inv.discount_amount
    assert loaded.source_file == inv.source_file
    assert loaded.tax_rate == inv.tax_rate
    assert loaded.discount_rate == inv.discount_rate
    assert isinstance(loaded.line_items, tuple)
    assert len(loaded.line_items) == 2
    for orig, got in zip(inv.line_items, loaded.line_items, strict=True):
        assert got.line_no == orig.line_no
        assert got.description == orig.description
        assert got.quantity == orig.quantity
        assert got.unit_price == orig.unit_price
        assert got.amount == orig.amount
        assert got.unit_of_measure == orig.unit_of_measure
        assert isinstance(got.quantity, Decimal)
        assert isinstance(got.unit_price, Decimal)
        assert isinstance(got.amount, Decimal)


def test_po_round_trip(pg_session):
    po = mk_po(
        po_number="PO-RT-1",
        vendor_name="Acme Corp",
        total="495.00",
        line_items=(mk_line(1, "Widget"), mk_line(2, "Gadget", qty="3.0", unit_price="10.00", amount="30.00")),
        currency="USD",
    )
    PurchaseOrderRepository.save(pg_session, po)
    loaded = PurchaseOrderRepository.load(pg_session, po.po_number)
    assert loaded == po
    assert type(loaded) is PurchaseOrder
    assert isinstance(loaded.line_items, tuple)
    assert loaded.line_items[0].unit_price == Decimal("45.00")


def test_grni_round_trip(pg_session):
    grni = mk_grni(
        grn_number="GRN-RT-1",
        vendor_name="Acme Corp",
        line_items=(mk_line(1, "Widget", qty="5.0", unit_price=None, amount=None),),
    )
    GRNIRepository.save(pg_session, grni)
    loaded = GRNIRepository.load(pg_session, grni.grn_number)
    assert loaded == grni
    assert type(loaded) is GRNI
    assert isinstance(loaded.line_items, tuple)
    assert loaded.line_items[0].quantity == Decimal("5.0")


def test_pard_round_trip(pg_session):
    inv = mk_invoice(invoice_number="INV-PARD-RT")
    InvoiceRepository.save(pg_session, inv)
    pard = mk_pard(pard_number="PARD-RT-1", invoice_number="INV-PARD-RT", amount="495.00", reference="REF-1")
    PaymentAdviceRepository.save(pg_session, pard)
    loaded = PaymentAdviceRepository.load(pg_session, pard.pard_number)
    assert loaded == pard
    assert type(loaded) is PaymentAdvice
    assert loaded.amount == Decimal("495.00")
    assert loaded.invoice_number == "INV-PARD-RT"


# --- Decimal precision survives ---------------------------------------------


def test_decimal_precision_4dp_preserved(pg_session):
    inv = mk_invoice(
        invoice_number="INV-4DP",
        line_items=(mk_line(1, "Widget", unit_price="45.1234", amount="451.2340"),),
    )
    InvoiceRepository.save(pg_session, inv)
    loaded = InvoiceRepository.load(pg_session, inv.invoice_number)
    assert loaded.line_items[0].unit_price == Decimal("45.1234")
    assert loaded.line_items[0].amount == Decimal("451.2340")


def test_large_total_precision(pg_session):
    inv = mk_invoice(invoice_number="INV-LARGE", total="99999999999999.9999")
    InvoiceRepository.save(pg_session, inv)
    loaded = InvoiceRepository.load(pg_session, inv.invoice_number)
    assert loaded.total == Decimal("99999999999999.9999")


def test_zero_decimals_preserved(pg_session):
    inv = mk_invoice(invoice_number="INV-ZERO", total="0.00")
    InvoiceRepository.save(pg_session, inv)
    loaded = InvoiceRepository.load(pg_session, inv.invoice_number)
    assert loaded.total == Decimal("0.00")
    assert isinstance(loaded.total, Decimal)


def test_negative_amount_if_schema_allows(pg_session):
    # Numeric(18,4) has no CHECK constraint, so negative values are allowed.
    inv = mk_invoice(
        invoice_number="INV-NEG",
        line_items=(mk_line(1, "Credit", qty="1.0", unit_price="-10.00", amount="-10.00"),),
    )
    InvoiceRepository.save(pg_session, inv)
    loaded = InvoiceRepository.load(pg_session, inv.invoice_number)
    assert loaded.line_items[0].amount == Decimal("-10.00")


# --- Optional fields ---------------------------------------------------------


def test_invoice_optional_fields_none(pg_session):
    inv = mk_invoice(
        invoice_number="INV-OPT",
        po_number=None,
        grn_number=None,
        vendor_tax_id=None,
        discount_amount=None,
        source_file=None,
        tax_rate=None,
        discount_rate=None,
    )
    InvoiceRepository.save(pg_session, inv)
    loaded = InvoiceRepository.load(pg_session, inv.invoice_number)
    assert loaded == inv
    assert loaded.po_number is None
    assert loaded.grn_number is None
    assert loaded.vendor_tax_id is None
    assert loaded.discount_amount is None
    assert loaded.source_file is None
    assert loaded.tax_rate is None
    assert loaded.discount_rate is None


def test_grni_line_price_none(pg_session):
    grni = mk_grni(
        grn_number="GRN-PRICE-NULL",
        line_items=(mk_line(1, "Widget", qty="5.0", unit_price=None, amount=None),),
    )
    GRNIRepository.save(pg_session, grni)
    loaded = GRNIRepository.load(pg_session, grni.grn_number)
    assert loaded == grni
    assert loaded.line_items[0].unit_price is None
    assert loaded.line_items[0].amount is None


# --- Upsert semantics --------------------------------------------------------


def test_save_twice_replaces(pg_session):
    inv1 = mk_invoice(invoice_number="INV-UPSERT", total="100.00", vendor_name="Old Vendor")
    InvoiceRepository.save(pg_session, inv1)
    inv2 = mk_invoice(invoice_number="INV-UPSERT", total="200.00", vendor_name="New Vendor")
    InvoiceRepository.save(pg_session, inv2)
    loaded = InvoiceRepository.load(pg_session, "INV-UPSERT")
    assert loaded == inv2
    assert loaded.total == Decimal("200.00")
    assert loaded.vendor_name == "New Vendor"


def test_save_twice_line_count_correct(pg_session):
    inv1 = mk_invoice(
        invoice_number="INV-LINES",
        line_items=(mk_line(1, "A"), mk_line(2, "B"), mk_line(3, "C")),
    )
    InvoiceRepository.save(pg_session, inv1)
    inv2 = mk_invoice(
        invoice_number="INV-LINES",
        line_items=(mk_line(1, "A"), mk_line(2, "B")),
    )
    InvoiceRepository.save(pg_session, inv2)
    loaded = InvoiceRepository.load(pg_session, "INV-LINES")
    assert len(loaded.line_items) == 2
    assert loaded == inv2


# --- Existence and deletion --------------------------------------------------


def test_exists_true_after_save(pg_session):
    inv = mk_invoice(invoice_number="INV-EXISTS")
    InvoiceRepository.save(pg_session, inv)
    assert InvoiceRepository.exists(pg_session, inv.invoice_number) is True


def test_exists_false_before_save(pg_session):
    assert InvoiceRepository.exists(pg_session, "INV-NONE") is False


def test_load_missing_raises_document_not_found(pg_session):
    with pytest.raises(DocumentNotFound) as exc_info:
        InvoiceRepository.load(pg_session, "INV-MISSING")
    exc = exc_info.value
    assert exc.kind is DocumentKind.INVOICE
    assert exc.identifier == "INV-MISSING"
    assert "INV-MISSING" in str(exc)
    assert "invoice" in str(exc)


def test_delete_removes_header_and_lines(pg_session):
    inv = mk_invoice(
        invoice_number="INV-DEL",
        line_items=(mk_line(1, "A"), mk_line(2, "B")),
    )
    InvoiceRepository.save(pg_session, inv)
    assert InvoiceRepository.exists(pg_session, inv.invoice_number) is True
    InvoiceRepository.delete(pg_session, inv.invoice_number)
    assert InvoiceRepository.exists(pg_session, inv.invoice_number) is False
    with pytest.raises(DocumentNotFound):
        InvoiceRepository.load(pg_session, inv.invoice_number)


# --- Transaction boundary ----------------------------------------------------


def test_rollback_leaves_no_partial_state(pg_engine):
    inv = mk_invoice(invoice_number="INV-ROLLBACK")
    with Session(pg_engine) as session:
        InvoiceRepository.save(session, inv)
        session.rollback()
    with Session(pg_engine) as session2:
        assert InvoiceRepository.exists(session2, inv.invoice_number) is False
