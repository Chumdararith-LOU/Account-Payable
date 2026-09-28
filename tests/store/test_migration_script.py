"""Tests for the dev-only SQLite -> Postgres migration script.

These run against a tmp COPY of ap_automation.db (the ``sqlite_copy`` fixture)
so the developer's real file is never touched. Marked ``migration`` (dev-only).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apmatch.store.repositories import (
    GRNIRepository,
    InvoiceRepository,
    PaymentAdviceRepository,
    PurchaseOrderRepository,
)
from scripts.migrate_sqlite_to_pg import _dec, migrate


@pytest.mark.migration
def test_dec_converts_float_via_str():
    # Preserves the source float's decimal representation; does NOT round.
    assert _dec(1100.0000000000002) == Decimal("1100.0000000000002")


@pytest.mark.migration
def test_dec_none_passthrough():
    assert _dec(None) is None


@pytest.mark.migration
def test_migration_idempotent(pg_session, sqlite_copy):
    migrate(sqlite_copy, pg_session)
    inv1 = InvoiceRepository.load(pg_session, "INV-2026-1123")
    migrate(sqlite_copy, pg_session)
    inv2 = InvoiceRepository.load(pg_session, "INV-2026-1123")
    assert len(inv1.line_items) == len(inv2.line_items) == 3


@pytest.mark.migration
def test_migration_writes_all_documents(pg_session, sqlite_copy):
    migrate(sqlite_copy, pg_session)
    assert InvoiceRepository.exists(pg_session, "INV-2026-1123")
    assert PurchaseOrderRepository.exists(pg_session, "PO-2026-0451")
    assert GRNIRepository.exists(pg_session, "GRN-2026-0322")
    assert PaymentAdviceRepository.exists(pg_session, "PARD-2026-0210")


@pytest.mark.migration
def test_migration_derives_totals_when_source_zero(pg_session, sqlite_copy):
    # Legacy Total/Amount were 0; the migrator derives them from the lines
    # (see the "Derivation policy" in the script docstring).
    migrate(sqlite_copy, pg_session)
    inv = InvoiceRepository.load(pg_session, "INV-2026-1123")
    assert inv.total == Decimal("1000")
    assert inv.subtotal == Decimal("1000")
    po = PurchaseOrderRepository.load(pg_session, "PO-2026-0451")
    assert po.total == Decimal("2000")
    pard = PaymentAdviceRepository.load(pg_session, "PARD-2026-0210")
    assert pard.amount == Decimal("1000")


@pytest.mark.migration
def test_migrated_invoice_passes_validation(pg_session, sqlite_copy):
    from apmatch.validation.arithmetic import validate_invoice

    migrate(sqlite_copy, pg_session)
    inv = InvoiceRepository.load(pg_session, "INV-2026-1123")
    result = validate_invoice(inv)
    assert result.has_blocker is False


@pytest.mark.migration
def test_migrated_po_has_nonzero_total_if_lines_present(pg_session, sqlite_copy):
    migrate(sqlite_copy, pg_session)
    po = PurchaseOrderRepository.load(pg_session, "PO-2026-0451")
    if po.line_items:
        assert po.total == sum(l.amount for l in po.line_items if l.amount is not None)


@pytest.mark.migration
def test_line_amount_equals_qty_times_price(pg_session, sqlite_copy):
    from apmatch.schema.documents import MONEY_QUANTUM, ROUND_HALF_UP

    migrate(sqlite_copy, pg_session)
    inv = InvoiceRepository.load(pg_session, "INV-2026-1123")
    for line in inv.line_items:
        if line.unit_price is not None:
            expected = (line.quantity * line.unit_price).quantize(MONEY_QUANTUM, ROUND_HALF_UP)
            assert line.amount == expected
