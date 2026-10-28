"""APPEND-ONLY audit log repository.

The only write method is ``append``. No ``update``. No ``delete``. No
``upsert``. The absence of these methods is a contract; if a future need
arises, it is a schema-level decision (a new superseding row), not a mutable
operation.

Caller manages transactions (same pattern as P1-10b). Failure tuples are
serialized to JSONB arrays of structured dicts on write and deserialized back
to the dataclass tuples on read; order is preserved (a contract from P1-06 and
P1-08b).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from apmatch.audit.entry import AuditEntry
from apmatch.audit.models import AuditLog
from apmatch.matching.result import MatchCode, MatchFailure, SimilarityMatch
from apmatch.scoring.result import Route, RouteReason
from apmatch.validation.result import CheckCode, CheckFailure, Severity


class AuditConflict(Exception):
    """Raised when append() is called with a run_id that already exists.

    Two runs with the same UUID indicate a bug (UUID collision or a retry that
    should have regenerated the ID); silently overwriting would destroy the
    audit trail.
    """

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"audit entry already exists for run_id {run_id!r}")


class AuditEntryNotFound(Exception):
    """Raised when get() is called with a run_id that does not exist."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"audit entry not found for run_id {run_id!r}")


def _failure_to_dict(failure) -> dict:
    return {
        "code": failure.code.value,
        "severity": failure.severity.value,
        "location": failure.location,
        "expected": failure.expected,
        "actual": failure.actual,
        "delta": failure.delta,
    }


def _dict_to_check_failure(d: dict) -> CheckFailure:
    return CheckFailure(
        code=CheckCode(d["code"]),
        severity=Severity(d["severity"]),
        location=d["location"],
        expected=d["expected"],
        actual=d["actual"],
        delta=d["delta"],
    )


def _dict_to_match_failure(d: dict) -> MatchFailure:
    return MatchFailure(
        code=MatchCode(d["code"]),
        severity=Severity(d["severity"]),
        location=d["location"],
        expected=d["expected"],
        actual=d["actual"],
        delta=d["delta"],
    )


def _serialize_similarity_matches(matches: tuple[SimilarityMatch, ...]) -> list[dict]:
    """SimilarityMatch tuple -> JSONB-ready list of dicts (Decimals as str)."""
    return [
        {
            "location": sm.location,
            "invoice_text": sm.invoice_text,
            "counterpart_text": sm.counterpart_text,
            "score": str(sm.score),
            "threshold_review": str(sm.threshold_review),
            "threshold_accept": str(sm.threshold_accept),
            "band": sm.band,
            "model_version": sm.model_version,
        }
        for sm in matches
    ]


def _deserialize_similarity_matches(raw: list[dict]) -> tuple[SimilarityMatch, ...]:
    """JSONB list of dicts -> SimilarityMatch tuple (Decimals reconstructed)."""
    return tuple(
        SimilarityMatch(
            location=d["location"],
            invoice_text=d["invoice_text"],
            counterpart_text=d["counterpart_text"],
            score=Decimal(d["score"]),
            threshold_review=Decimal(d["threshold_review"]),
            threshold_accept=Decimal(d["threshold_accept"]),
            band=d["band"],
            model_version=d["model_version"],
        )
        for d in raw
    )


class AuditRepository:
    """APPEND-ONLY. The only write method is ``append``."""

    @staticmethod
    def append(session: Session, entry: AuditEntry) -> None:
        if session.get(AuditLog, entry.run_id) is not None:
            raise AuditConflict(entry.run_id)
        session.add(
            AuditLog(
                run_id=entry.run_id,
                run_timestamp=entry.run_timestamp,
                invoice_number=entry.invoice_number,
                customer_id=entry.customer_id,
                po_number=entry.po_number,
                grn_number=entry.grn_number,
                pard_ref=entry.pard_ref,
                route=entry.route.value,
                route_reason=entry.route_reason.value,
                score_value=entry.score_value,
                remark=entry.remark,
                validation_failures=[_failure_to_dict(f) for f in entry.validation_failures],
                match_failures=[_failure_to_dict(f) for f in entry.match_failures],
                input_hash=entry.input_hash,
                similarity_matches=_serialize_similarity_matches(entry.similarity_matches),
            )
        )
        session.flush()

    @staticmethod
    def _row_to_entry(row: AuditLog) -> AuditEntry:
        return AuditEntry(
            run_id=row.run_id,
            run_timestamp=row.run_timestamp,
            invoice_number=row.invoice_number,
            customer_id=row.customer_id,
            po_number=row.po_number,
            grn_number=row.grn_number,
            pard_ref=row.pard_ref,
            route=Route(row.route),
            route_reason=RouteReason(row.route_reason),
            score_value=row.score_value,
            remark=row.remark,
            validation_failures=tuple(_dict_to_check_failure(d) for d in row.validation_failures),
            match_failures=tuple(_dict_to_match_failure(d) for d in row.match_failures),
            input_hash=row.input_hash,
            similarity_matches=_deserialize_similarity_matches(row.similarity_matches),
        )

    @staticmethod
    def get(session: Session, run_id: str) -> AuditEntry:
        row = session.get(AuditLog, run_id)
        if row is None:
            raise AuditEntryNotFound(run_id)
        return AuditRepository._row_to_entry(row)

    @staticmethod
    def list_recent(session: Session, limit: int = 100) -> tuple[AuditEntry, ...]:
        rows = session.execute(
            select(AuditLog)
            .order_by(AuditLog.run_timestamp.desc(), AuditLog.run_id.desc())
            .limit(limit)
        ).scalars().all()
        return tuple(AuditRepository._row_to_entry(row) for row in rows)

    # NOT DEFINED, BY DESIGN:
    #   update
    #   delete
    #   upsert
