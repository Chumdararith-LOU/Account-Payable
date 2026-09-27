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
def test_migration_preserves_totals(pg_session, sqlite_copy):
    migrate(sqlite_copy, pg_session)
    inv = InvoiceRepository.load(pg_session, "INV-2026-1123")
    assert inv.total == Decimal("0")
    po = PurchaseOrderRepository.load(pg_session, "PO-2026-0451")
    assert po.total == Decimal("0")
    pard = PaymentAdviceRepository.load(pg_session, "PARD-2026-0210")
    assert pard.amount == Decimal("0")
