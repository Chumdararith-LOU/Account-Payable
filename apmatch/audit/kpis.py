"""Read-only KPI queries over the append-only audit log.

Read-only over ``audit_log``. Each function returns a bounded structure (no
iterators, no generators). All aggregates are computed by Postgres, not in
Python. No caching; correctness over throughput today. Functions never call
``commit`` and never return ORM instances — only the frozen dataclasses below.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apmatch.audit.models import AuditLog
from apmatch.scoring.result import Route, RouteReason


@dataclass(frozen=True)
class RouteCounts:
    auto_approve: int
    human_review: int
    reject: int

    @property
    def total(self) -> int:
        return self.auto_approve + self.human_review + self.reject


@dataclass(frozen=True)
class ReasonCounts:
    reason: RouteReason
    count: int


@dataclass(frozen=True)
class RecentRun:
    run_id: str
    run_timestamp: datetime
    invoice_number: str
    route: Route
    route_reason: RouteReason
    score_value: Decimal
    remark: str


@dataclass(frozen=True)
class ScoreBuckets:
    # 5 fixed buckets over [0.0, 1.0]; each lower bound is inclusive, upper exclusive.
    b_00_02: int  # score < 0.2
    b_02_04: int  # 0.2 <= score < 0.4
    b_04_06: int  # 0.4 <= score < 0.6
    b_06_08: int  # 0.6 <= score < 0.8
    b_08_10: int  # score >= 0.8


def _row_to_recent_run(row: AuditLog) -> RecentRun:
    return RecentRun(
        run_id=row.run_id,
        run_timestamp=row.run_timestamp,
        invoice_number=row.invoice_number,
        route=Route(row.route),
        route_reason=RouteReason(row.route_reason),
        score_value=row.score_value,
        remark=row.remark,
    )


def count_by_route(session: Session, since: datetime | None = None) -> RouteCounts:
    """Count runs grouped by route, optionally filtered to run_timestamp >= since."""
    stmt = select(AuditLog.route, func.count()).group_by(AuditLog.route)
    if since is not None:
        stmt = stmt.where(AuditLog.run_timestamp >= since)
    counts = {route: count for route, count in session.execute(stmt).all()}
    return RouteCounts(
        auto_approve=counts.get(Route.AUTO_APPROVE.value, 0),
        human_review=counts.get(Route.HUMAN_REVIEW.value, 0),
        reject=counts.get(Route.REJECT.value, 0),
    )


def count_by_reason(session: Session, since: datetime | None = None) -> tuple[ReasonCounts, ...]:
    """Count runs grouped by route_reason, ordered by count DESC then reason ASC."""
    stmt = (
        select(AuditLog.route_reason, func.count().label("count"))
        .group_by(AuditLog.route_reason)
        .order_by(func.count().desc(), AuditLog.route_reason.asc())
    )
    if since is not None:
        stmt = stmt.where(AuditLog.run_timestamp >= since)
    return tuple(
        ReasonCounts(reason=RouteReason(reason), count=count)
        for reason, count in session.execute(stmt).all()
    )


def recent_runs(session: Session, limit: int = 50) -> tuple[RecentRun, ...]:
    """Most recent runs first (run_timestamp DESC, run_id DESC), bounded limit."""
    if limit < 1 or limit > 500:
        raise ValueError(f"limit must be between 1 and 500, got {limit}")
    stmt = (
        select(AuditLog)
        .order_by(AuditLog.run_timestamp.desc(), AuditLog.run_id.desc())
        .limit(limit)
    )
    return tuple(_row_to_recent_run(row) for row in session.execute(stmt).scalars().all())


def score_histogram(session: Session, since: datetime | None = None) -> ScoreBuckets:
    """5 fixed score buckets computed in a single Postgres query (COUNT FILTER)."""
    s = AuditLog.score_value
    stmt = select(
        func.count().filter(s < Decimal("0.2")).label("b_00_02"),
        func.count().filter((s >= Decimal("0.2")) & (s < Decimal("0.4"))).label("b_02_04"),
        func.count().filter((s >= Decimal("0.4")) & (s < Decimal("0.6"))).label("b_04_06"),
        func.count().filter((s >= Decimal("0.6")) & (s < Decimal("0.8"))).label("b_06_08"),
        func.count().filter(s >= Decimal("0.8")).label("b_08_10"),
    )
    if since is not None:
        stmt = stmt.where(AuditLog.run_timestamp >= since)
    row = session.execute(stmt).one()
    return ScoreBuckets(
        b_00_02=row.b_00_02,
        b_02_04=row.b_02_04,
        b_04_06=row.b_04_06,
        b_06_08=row.b_06_08,
        b_08_10=row.b_08_10,
    )


def top_discrepancy_invoices(
    session: Session, limit: int = 10, since: datetime | None = None
) -> tuple[RecentRun, ...]:
    """Most recent HUMAN_REVIEW/REJECT runs, lowest confidence first.

    Ordered by score_value ASC (lowest confidence first), then run_timestamp DESC.
    """
    if limit < 1 or limit > 100:
        raise ValueError(f"limit must be between 1 and 100, got {limit}")
    stmt = (
        select(AuditLog)
        .where(AuditLog.route.in_([Route.HUMAN_REVIEW.value, Route.REJECT.value]))
        .order_by(AuditLog.score_value.asc(), AuditLog.run_timestamp.desc())
        .limit(limit)
    )
    if since is not None:
        stmt = stmt.where(AuditLog.run_timestamp >= since)
    return tuple(_row_to_recent_run(row) for row in session.execute(stmt).scalars().all())
