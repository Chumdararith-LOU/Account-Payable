"""Fixtures for the audit tests.

Reuses the Postgres fixtures from ``tests/store/conftest.py`` (same engine,
same schema, same per-test rollback). Adds an ``AuditEntry`` builder.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from apmatch.audit.entry import AuditEntry
from apmatch.scoring.result import Route, RouteReason
from tests.store.conftest import pg_engine, pg_session  # noqa: F401  (re-exported)


@pytest.fixture
def _mk_audit_entry():
    """Builder returning an :class:`AuditEntry`; kwargs override the defaults."""

    def _build(**kwargs) -> AuditEntry:
        return AuditEntry(
            run_id=kwargs.get("run_id") or uuid4().hex,
            run_timestamp=kwargs.get("run_timestamp") or datetime.now(UTC),
            invoice_number=kwargs.get("invoice_number", "INV-AUDIT-1"),
            po_number=kwargs.get("po_number", "PO-AUDIT-1"),
            grn_number=kwargs.get("grn_number", "GRN-AUDIT-1"),
            pard_ref=kwargs.get("pard_ref", "PARD-AUDIT-1"),
            route=kwargs.get("route", Route.AUTO_APPROVE),
            route_reason=kwargs.get("route_reason", RouteReason.ALL_CHECKS_PASSED),
            score_value=kwargs.get("score_value", Decimal("0.9500")),
            remark=kwargs.get("remark", "Validated OK."),
            validation_failures=kwargs.get("validation_failures", ()),
            match_failures=kwargs.get("match_failures", ()),
            input_hash=kwargs.get("input_hash", "0" * 64),
            similarity_matches=kwargs.get("similarity_matches", ()),
        )

    return _build
