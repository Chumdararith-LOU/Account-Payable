"""Read-only KPI queries over the append-only audit log.

Read-only over ``audit_log``. Each function returns a bounded structure (no
iterators, no generators). All aggregates are computed by Postgres, not in
Python. No caching; correctness over throughput today. Functions never call
``commit`` and never return ORM instances — only the frozen dataclasses below.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select, true
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
    case_id: str | None = None
    customer_id: str = "default"
    decided_by: str = "system"


@dataclass(frozen=True)
class CodeCount:
    code: str
    count: int


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
        case_id=row.case_id or row.run_id,
        customer_id=row.customer_id,
        decided_by=row.decided_by,
    )


def _latest_per_case(customer_id: str | None = None):
    """Subquery: the newest run of every case (corrections supersede earlier runs)."""
    case_key = func.coalesce(AuditLog.case_id, AuditLog.run_id)
    stmt = (
        select(AuditLog.run_id)
        .distinct(case_key)
        .order_by(case_key, AuditLog.run_timestamp.desc(), AuditLog.run_id.desc())
    )
    if customer_id is not None:
        stmt = stmt.where(AuditLog.customer_id == customer_id)
    return stmt.subquery()


def count_cases_by_route(session: Session, customer_id: str | None = None) -> RouteCounts:
    """Route counts over CASES (latest run of each), not over runs."""
    latest = _latest_per_case(customer_id)
    stmt = (
        select(AuditLog.route, func.count())
        .where(AuditLog.run_id.in_(select(latest.c.run_id)))
        .group_by(AuditLog.route)
    )
    counts = {route: count for route, count in session.execute(stmt).all()}
    return RouteCounts(
        auto_approve=counts.get(Route.AUTO_APPROVE.value, 0),
        human_review=counts.get(Route.HUMAN_REVIEW.value, 0),
        reject=counts.get(Route.REJECT.value, 0),
    )


def review_queue(session: Session, customer_id: str | None = None, limit: int = 200) -> tuple[RecentRun, ...]:
    """Cases whose latest run is HUMAN_REVIEW, oldest first (first in, first out)."""
    if limit < 1 or limit > 500:
        raise ValueError(f"limit must be between 1 and 500, got {limit}")
    latest = _latest_per_case(customer_id)
    stmt = (
        select(AuditLog)
        .where(AuditLog.run_id.in_(select(latest.c.run_id)))
        .where(AuditLog.route == Route.HUMAN_REVIEW.value)
        .order_by(AuditLog.run_timestamp.asc(), AuditLog.run_id.asc())
        .limit(limit)
    )
    return tuple(_row_to_recent_run(row) for row in session.execute(stmt).scalars().all())


def case_history(session: Session, case_id: str) -> tuple[RecentRun, ...]:
    """Every run of one case, oldest first."""
    stmt = (
        select(AuditLog)
        .where(func.coalesce(AuditLog.case_id, AuditLog.run_id) == case_id)
        .order_by(AuditLog.run_timestamp.asc(), AuditLog.run_id.asc())
    )
    return tuple(_row_to_recent_run(row) for row in session.execute(stmt).scalars().all())


def list_customers(session: Session) -> tuple[str, ...]:
    stmt = select(AuditLog.customer_id).distinct().order_by(AuditLog.customer_id)
    return tuple(session.execute(stmt).scalars().all())


def failure_code_counts(
    session: Session, customer_id: str | None = None, limit: int = 8
) -> tuple[CodeCount, ...]:
    """Most frequent failure codes over the latest run of every case (computed in Postgres)."""
    latest = _latest_per_case(customer_id)
    f = (
        func.jsonb_array_elements(AuditLog.validation_failures.op("||")(AuditLog.match_failures))
        .table_valued("value")
        .render_derived(name="f")
    )
    code = f.c.value.op("->>")("code")
    stmt = (
        select(code.label("code"), func.count().label("n"))
        .select_from(AuditLog)
        .join(f, true())
        .where(AuditLog.run_id.in_(select(latest.c.run_id)))
        .group_by(code)
        .order_by(func.count().desc(), code.asc())
        .limit(limit)
    )
    return tuple(CodeCount(code=c, count=n) for c, n in session.execute(stmt).all())


def count_by_route(
    session: Session, since: datetime | None = None, customer_id: str | None = None
) -> RouteCounts:
    """Count runs grouped by route, optionally filtered by since and customer_id."""
    stmt = select(AuditLog.route, func.count()).group_by(AuditLog.route)
    if since is not None:
        stmt = stmt.where(AuditLog.run_timestamp >= since)
    if customer_id is not None:
        stmt = stmt.where(AuditLog.customer_id == customer_id)
    counts = {route: count for route, count in session.execute(stmt).all()}
    return RouteCounts(
        auto_approve=counts.get(Route.AUTO_APPROVE.value, 0),
        human_review=counts.get(Route.HUMAN_REVIEW.value, 0),
        reject=counts.get(Route.REJECT.value, 0),
    )


def count_by_reason(
    session: Session, since: datetime | None = None, customer_id: str | None = None
) -> tuple[ReasonCounts, ...]:
    """Count runs grouped by route_reason, ordered by count DESC then reason ASC."""
    stmt = (
        select(AuditLog.route_reason, func.count().label("count"))
        .group_by(AuditLog.route_reason)
        .order_by(func.count().desc(), AuditLog.route_reason.asc())
    )
    if since is not None:
        stmt = stmt.where(AuditLog.run_timestamp >= since)
    if customer_id is not None:
        stmt = stmt.where(AuditLog.customer_id == customer_id)
    return tuple(
        ReasonCounts(reason=RouteReason(reason), count=count)
        for reason, count in session.execute(stmt).all()
    )


def recent_runs(
    session: Session, limit: int = 50, customer_id: str | None = None
) -> tuple[RecentRun, ...]:
    """Most recent runs first (run_timestamp DESC, run_id DESC), bounded limit."""
    if limit < 1 or limit > 500:
        raise ValueError(f"limit must be between 1 and 500, got {limit}")
    stmt = (
        select(AuditLog)
        .order_by(AuditLog.run_timestamp.desc(), AuditLog.run_id.desc())
        .limit(limit)
    )
    if customer_id is not None:
        stmt = stmt.where(AuditLog.customer_id == customer_id)
    return tuple(_row_to_recent_run(row) for row in session.execute(stmt).scalars().all())


def score_histogram(
    session: Session, since: datetime | None = None, customer_id: str | None = None
) -> ScoreBuckets:
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
    if customer_id is not None:
        stmt = stmt.where(AuditLog.customer_id == customer_id)
    row = session.execute(stmt).one()
    return ScoreBuckets(
        b_00_02=row.b_00_02,
        b_02_04=row.b_02_04,
        b_04_06=row.b_04_06,
        b_06_08=row.b_06_08,
        b_08_10=row.b_08_10,
    )


def top_discrepancy_invoices(
    session: Session,
    limit: int = 10,
    since: datetime | None = None,
    customer_id: str | None = None,
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
    if customer_id is not None:
        stmt = stmt.where(AuditLog.customer_id == customer_id)
    return tuple(_row_to_recent_run(row) for row in session.execute(stmt).scalars().all())


def find_prior_invoice_run(
    session: Session,
    *,
    vendor_tax_id: str | None,
    invoice_number: str,
    invoice_date: date | None,
    total: Decimal | None,
    customer_id: str | None = None,
    exclude_case_id: str | None = None,
) -> str | None:
    """Return the run_id of any prior run for the same invoice_number, or None.

    Conservative MVP: matches on exact invoice_number only. Catches the most
    common duplicate — an invoice that was processed once and is now
    resubmitted — regardless of the prior run's route (a prior REJECT-then-
    resubmit is exactly the pattern worth flagging). The other three
    parameters are reserved for the supplier-aware extension that waits on
    audit_log.vendor_tax_id (DECISIONS.md D-108); they are unused today.
    Read-only; no commit; single-row response.
    """
    if not invoice_number:
        return None
    stmt = select(AuditLog.run_id).where(AuditLog.invoice_number == invoice_number)
    # Another customer's supplier may use the same number: not a duplicate.
    if customer_id is not None:
        stmt = stmt.where(AuditLog.customer_id == customer_id)
    # A reviewer's re-check of the same submission is not a resubmission.
    if exclude_case_id is not None:
        stmt = stmt.where(func.coalesce(AuditLog.case_id, AuditLog.run_id) != exclude_case_id)
    return session.execute(stmt.order_by(AuditLog.run_timestamp.asc()).limit(1)).scalar_one_or_none()
