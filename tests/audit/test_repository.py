"""Round-trip and append-only contract tests for the audit repository.

Run against a real Postgres (skipped if unreachable, via the re-exported
``pg_session`` fixture).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from apmatch.audit.entry import AuditEntry
from apmatch.audit.repository import (
    AuditConflict,
    AuditEntryNotFound,
    AuditRepository,
)
from apmatch.matching.result import MatchCode, MatchFailure, SimilarityMatch
from apmatch.validation.result import CheckCode, CheckFailure, Severity


def _check_failure() -> CheckFailure:
    return CheckFailure(
        code=CheckCode.TOTAL_MISMATCH,
        severity=Severity.BLOCKER,
        location="header",
        expected="100.00",
        actual="99.00",
        delta="1.00",
    )


def _match_failure() -> MatchFailure:
    return MatchFailure(
        code=MatchCode.QTY_MISMATCH,
        severity=Severity.WARNING,
        location="line 1 (INV) -> line 1 (PO)",
        expected="10",
        actual="9",
        delta="1",
    )


def test_append_and_get_roundtrip(pg_session, _mk_audit_entry):
    entry = _mk_audit_entry(
        run_id="a" * 32,
        score_value=Decimal("0.8750"),
        validation_failures=(_check_failure(),),
        match_failures=(_match_failure(),),
        input_hash="f" * 64,
    )
    AuditRepository.append(pg_session, entry)
    loaded = AuditRepository.get(pg_session, entry.run_id)

    assert type(loaded) is AuditEntry
    assert loaded == entry
    assert loaded.run_id == entry.run_id
    assert loaded.invoice_number == entry.invoice_number
    assert loaded.route is entry.route
    assert loaded.route_reason is entry.route_reason
    assert loaded.score_value == Decimal("0.8750")
    assert isinstance(loaded.score_value, Decimal)
    assert loaded.validation_failures == entry.validation_failures
    assert loaded.match_failures == entry.match_failures
    assert loaded.input_hash == entry.input_hash


def test_append_duplicate_run_id_raises_conflict(pg_session, _mk_audit_entry):
    entry = _mk_audit_entry(run_id="b" * 32)
    AuditRepository.append(pg_session, entry)
    with pytest.raises(AuditConflict):
        AuditRepository.append(pg_session, entry)


def test_get_missing_raises_not_found(pg_session):
    with pytest.raises(AuditEntryNotFound):
        AuditRepository.get(pg_session, "c" * 32)


def test_list_recent_orders_by_timestamp_desc(pg_session, _mk_audit_entry):
    base = datetime(2026, 1, 1, tzinfo=UTC)
    # Insert out of order: oldest, newest, middle.
    AuditRepository.append(pg_session, _mk_audit_entry(run_id="1" * 32, run_timestamp=base))
    AuditRepository.append(pg_session, _mk_audit_entry(run_id="3" * 32, run_timestamp=base + timedelta(hours=2)))
    AuditRepository.append(pg_session, _mk_audit_entry(run_id="2" * 32, run_timestamp=base + timedelta(hours=1)))
    recent = AuditRepository.list_recent(pg_session)
    assert [e.run_id for e in recent] == ["3" * 32, "2" * 32, "1" * 32]


def test_list_recent_limit(pg_session, _mk_audit_entry):
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(5):
        AuditRepository.append(
            pg_session,
            _mk_audit_entry(run_id=f"{i:032d}", run_timestamp=base + timedelta(hours=i)),
        )
    recent = AuditRepository.list_recent(pg_session, limit=3)
    assert len(recent) == 3
    assert recent[0].run_id == "00000000000000000000000000000004"


def test_no_update_method():
    assert not hasattr(AuditRepository, "update")


def test_no_delete_method():
    assert not hasattr(AuditRepository, "delete")


def test_no_upsert_method():
    assert not hasattr(AuditRepository, "upsert")


def test_failures_roundtrip_as_structured_data(pg_session, _mk_audit_entry):
    entry = _mk_audit_entry(
        run_id="d" * 32,
        validation_failures=(_check_failure(),),
        match_failures=(_match_failure(),),
    )
    AuditRepository.append(pg_session, entry)
    loaded = AuditRepository.get(pg_session, entry.run_id)
    vf = loaded.validation_failures[0]
    assert vf.code is CheckCode.TOTAL_MISMATCH
    assert vf.severity is Severity.BLOCKER
    assert vf.location == "header"
    assert vf.expected == "100.00"
    assert vf.actual == "99.00"
    assert vf.delta == "1.00"
    mf = loaded.match_failures[0]
    assert mf.code is MatchCode.QTY_MISMATCH
    assert mf.severity is Severity.WARNING
    assert mf.delta == "1"


def test_input_hash_survives_roundtrip(pg_session, _mk_audit_entry):
    entry = _mk_audit_entry(run_id="e" * 32, input_hash="a1" * 32)
    AuditRepository.append(pg_session, entry)
    loaded = AuditRepository.get(pg_session, entry.run_id)
    assert loaded.input_hash == "a1" * 32


def _similarity_match(band="accept", score="0.7433") -> SimilarityMatch:
    return SimilarityMatch(
        location="line 1 (INV) -> line 1 (PO)",
        invoice_text="office chair",
        counterpart_text="chair office metal frame black",
        score=Decimal(score),
        threshold_review=Decimal("0.55"),
        threshold_accept=Decimal("0.70"),
        band=band,
        model_version="f" * 64,
    )


def test_audit_entry_roundtrip_with_similarity_matches(pg_session, _mk_audit_entry):
    entry = _mk_audit_entry(
        run_id="f" * 32,
        similarity_matches=(
            _similarity_match(band="accept", score="0.7433"),
            _similarity_match(band="review", score="0.6000"),
        ),
    )
    AuditRepository.append(pg_session, entry)
    loaded = AuditRepository.get(pg_session, entry.run_id)
    assert loaded.similarity_matches == entry.similarity_matches
    assert len(loaded.similarity_matches) == 2
    first, second = loaded.similarity_matches
    assert first.score == Decimal("0.7433")
    assert isinstance(first.score, Decimal)
    assert first.threshold_review == Decimal("0.55")
    assert first.threshold_accept == Decimal("0.70")
    assert first.band == "accept"
    assert second.band == "review"
    assert second.score == Decimal("0.6000")
    assert first.model_version == "f" * 64


def test_audit_entry_roundtrip_without_similarity_matches(pg_session, _mk_audit_entry):
    entry = _mk_audit_entry(run_id="0" * 31 + "1")
    AuditRepository.append(pg_session, entry)
    loaded = AuditRepository.get(pg_session, entry.run_id)
    assert loaded.similarity_matches == ()


def test_audit_entry_roundtrip_preserves_customer_id(pg_session, _mk_audit_entry):
    entry = _mk_audit_entry(run_id="g" * 32, customer_id="hotel_acme")
    AuditRepository.append(pg_session, entry)
    loaded = AuditRepository.get(pg_session, entry.run_id)
    assert loaded.customer_id == "hotel_acme"


def test_audit_entry_default_customer_id(pg_session, _mk_audit_entry):
    entry = _mk_audit_entry(run_id="h" * 32)
    AuditRepository.append(pg_session, entry)
    loaded = AuditRepository.get(pg_session, entry.run_id)
    assert loaded.customer_id == "default"
