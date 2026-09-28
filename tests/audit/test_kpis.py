"""Tests for the read-only KPI queries over audit_log.

All tests use the existing ``pg_session`` fixture and ``_mk_audit_entry``
builder from P1-11a. Aggregates run in Postgres; the tests assert the bounded
dataclass results.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from apmatch.audit.kpis import (
    RouteCounts,
    ScoreBuckets,
    count_by_reason,
    count_by_route,
    recent_runs,
    score_histogram,
    top_discrepancy_invoices,
)
from apmatch.audit.repository import AuditRepository
from apmatch.scoring.result import Route, RouteReason


# --- Route counts -----------------------------------------------------------


def test_count_by_route_empty(pg_session):
    assert count_by_route(pg_session) == RouteCounts(0, 0, 0)


def test_count_by_route_all(pg_session, _mk_audit_entry):
    AuditRepository.append(pg_session, _mk_audit_entry(run_id="1" * 32, route=Route.AUTO_APPROVE))
    AuditRepository.append(pg_session, _mk_audit_entry(run_id="2" * 32, route=Route.HUMAN_REVIEW))
    AuditRepository.append(pg_session, _mk_audit_entry(run_id="3" * 32, route=Route.HUMAN_REVIEW))
    AuditRepository.append(pg_session, _mk_audit_entry(run_id="4" * 32, route=Route.REJECT))
    assert count_by_route(pg_session) == RouteCounts(1, 2, 1)


def test_count_by_route_since_filter(pg_session, _mk_audit_entry):
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    recent = datetime(2026, 6, 1, tzinfo=timezone.utc)
    cutoff = datetime(2026, 3, 1, tzinfo=timezone.utc)
    AuditRepository.append(pg_session, _mk_audit_entry(run_id="1" * 32, route=Route.AUTO_APPROVE, run_timestamp=old))
    AuditRepository.append(pg_session, _mk_audit_entry(run_id="2" * 32, route=Route.AUTO_APPROVE, run_timestamp=old))
    AuditRepository.append(pg_session, _mk_audit_entry(run_id="3" * 32, route=Route.HUMAN_REVIEW, run_timestamp=recent))
    AuditRepository.append(pg_session, _mk_audit_entry(run_id="4" * 32, route=Route.HUMAN_REVIEW, run_timestamp=recent))
    AuditRepository.append(pg_session, _mk_audit_entry(run_id="5" * 32, route=Route.REJECT, run_timestamp=recent))
    assert count_by_route(pg_session, since=cutoff) == RouteCounts(0, 2, 1)


def test_count_by_route_total_property(pg_session, _mk_audit_entry):
    AuditRepository.append(pg_session, _mk_audit_entry(run_id="1" * 32, route=Route.AUTO_APPROVE))
    AuditRepository.append(pg_session, _mk_audit_entry(run_id="2" * 32, route=Route.HUMAN_REVIEW))
    AuditRepository.append(pg_session, _mk_audit_entry(run_id="3" * 32, route=Route.REJECT))
    assert count_by_route(pg_session).total == 3


# --- Reason counts ----------------------------------------------------------


def test_count_by_reason_empty(pg_session):
    assert count_by_reason(pg_session) == ()


def test_count_by_reason_ordered_by_count_desc(pg_session, _mk_audit_entry):
    for i in range(3):
        AuditRepository.append(pg_session, _mk_audit_entry(run_id=f"a{i:031d}", route_reason=RouteReason.ALL_CHECKS_PASSED))
    for i in range(2):
        AuditRepository.append(pg_session, _mk_audit_entry(run_id=f"b{i:031d}", route_reason=RouteReason.MATCH_DISCREPANCY))
    AuditRepository.append(pg_session, _mk_audit_entry(run_id="c" * 32, route_reason=RouteReason.VALIDATION_BLOCKER))
    reasons = count_by_reason(pg_session)
    assert [r.reason for r in reasons] == [
        RouteReason.ALL_CHECKS_PASSED,
        RouteReason.MATCH_DISCREPANCY,
        RouteReason.VALIDATION_BLOCKER,
    ]
    assert [r.count for r in reasons] == [3, 2, 1]


def test_count_by_reason_stable_tiebreak(pg_session, _mk_audit_entry):
    for i in range(2):
        AuditRepository.append(pg_session, _mk_audit_entry(run_id=f"a{i:031d}", route_reason=RouteReason.MATCH_DISCREPANCY))
    for i in range(2):
        AuditRepository.append(pg_session, _mk_audit_entry(run_id=f"b{i:031d}", route_reason=RouteReason.ALL_CHECKS_PASSED))
    reasons = count_by_reason(pg_session)
    # Both count=2 -> ordered by reason.value ASC.
    assert [r.reason for r in reasons] == [RouteReason.ALL_CHECKS_PASSED, RouteReason.MATCH_DISCREPANCY]


# --- Recent runs ------------------------------------------------------------


def test_recent_runs_empty(pg_session):
    assert recent_runs(pg_session) == ()


def test_recent_runs_most_recent_first(pg_session, _mk_audit_entry):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    AuditRepository.append(pg_session, _mk_audit_entry(run_id="1" * 32, run_timestamp=base))
    AuditRepository.append(pg_session, _mk_audit_entry(run_id="3" * 32, run_timestamp=base + timedelta(hours=2)))
    AuditRepository.append(pg_session, _mk_audit_entry(run_id="2" * 32, run_timestamp=base + timedelta(hours=1)))
    assert [r.run_id for r in recent_runs(pg_session)] == ["3" * 32, "2" * 32, "1" * 32]


def test_recent_runs_limit(pg_session, _mk_audit_entry):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(5):
        AuditRepository.append(pg_session, _mk_audit_entry(run_id=f"{i:032d}", run_timestamp=base + timedelta(hours=i)))
    assert len(recent_runs(pg_session, limit=3)) == 3


def test_recent_runs_rejects_invalid_limit(pg_session):
    with pytest.raises(ValueError):
        recent_runs(pg_session, limit=0)
    with pytest.raises(ValueError):
        recent_runs(pg_session, limit=501)


# --- Score histogram --------------------------------------------------------


def test_score_histogram_empty(pg_session):
    assert score_histogram(pg_session) == ScoreBuckets(0, 0, 0, 0, 0)


def test_score_histogram_all_buckets_populated(pg_session, _mk_audit_entry):
    for i, score in enumerate(["0.1000", "0.3000", "0.5000", "0.7000", "0.9000"]):
        AuditRepository.append(pg_session, _mk_audit_entry(run_id=f"{i:032d}", score_value=Decimal(score)))
    assert score_histogram(pg_session) == ScoreBuckets(1, 1, 1, 1, 1)


def test_score_histogram_boundary_values(pg_session, _mk_audit_entry):
    # Lower bound inclusive: 0.20->b_02_04, 0.40->b_04_06, 0.60->b_06_08, 0.80->b_08_10.
    for i, score in enumerate(["0.2000", "0.4000", "0.6000", "0.8000"]):
        AuditRepository.append(pg_session, _mk_audit_entry(run_id=f"{i:032d}", score_value=Decimal(score)))
    assert score_histogram(pg_session) == ScoreBuckets(0, 1, 1, 1, 1)


def test_score_histogram_zero_and_one(pg_session, _mk_audit_entry):
    AuditRepository.append(pg_session, _mk_audit_entry(run_id="0" * 32, score_value=Decimal("0.0000")))
    AuditRepository.append(pg_session, _mk_audit_entry(run_id="1" * 32, score_value=Decimal("1.0000")))
    buckets = score_histogram(pg_session)
    assert buckets.b_00_02 == 1
    assert buckets.b_08_10 == 1


# --- Top discrepancies ------------------------------------------------------


def test_top_discrepancy_invoices_empty(pg_session):
    assert top_discrepancy_invoices(pg_session) == ()


def test_top_discrepancy_invoices_filters_by_route(pg_session, _mk_audit_entry):
    AuditRepository.append(pg_session, _mk_audit_entry(run_id="1" * 32, route=Route.AUTO_APPROVE))
    AuditRepository.append(pg_session, _mk_audit_entry(run_id="2" * 32, route=Route.HUMAN_REVIEW))
    AuditRepository.append(pg_session, _mk_audit_entry(run_id="3" * 32, route=Route.REJECT))
    assert {r.run_id for r in top_discrepancy_invoices(pg_session)} == {"2" * 32, "3" * 32}


def test_top_discrepancy_invoices_ordered_by_score_asc(pg_session, _mk_audit_entry):
    AuditRepository.append(pg_session, _mk_audit_entry(run_id="1" * 32, route=Route.HUMAN_REVIEW, score_value=Decimal("0.9000")))
    AuditRepository.append(pg_session, _mk_audit_entry(run_id="2" * 32, route=Route.HUMAN_REVIEW, score_value=Decimal("0.5000")))
    AuditRepository.append(pg_session, _mk_audit_entry(run_id="3" * 32, route=Route.REJECT, score_value=Decimal("0.3000")))
    assert [r.run_id for r in top_discrepancy_invoices(pg_session)] == ["3" * 32, "2" * 32, "1" * 32]


def test_top_discrepancy_invoices_rejects_invalid_limit(pg_session):
    with pytest.raises(ValueError):
        top_discrepancy_invoices(pg_session, limit=0)
    with pytest.raises(ValueError):
        top_discrepancy_invoices(pg_session, limit=101)
