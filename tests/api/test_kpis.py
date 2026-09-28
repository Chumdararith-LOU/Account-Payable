"""GET /kpis/* — read-only KPI queries over the audit log.

Uses synthetic AuditEntry rows (no OCR needed) so the KPI tests stay fast.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from apmatch.audit.entry import AuditEntry
from apmatch.audit.repository import AuditRepository
from apmatch.scoring.result import Route, RouteReason


def _entry(route: Route) -> AuditEntry:
    return AuditEntry(
        run_id=uuid4().hex,
        run_timestamp=datetime.now(timezone.utc),
        invoice_number="INV-TEST",
        po_number=None,
        grn_number=None,
        pard_ref=None,
        route=route,
        route_reason=RouteReason.ALL_CHECKS_PASSED if route is Route.AUTO_APPROVE else RouteReason.LOW_OVERALL_SCORE,
        score_value=Decimal("0.9000"),
        remark="synthetic test entry",
        validation_failures=(),
        match_failures=(),
        input_hash="0" * 64,
    )


def test_kpis_routes_empty(client_tx, test_api_key):
    # A far-future `since` guarantees zero rows regardless of DB history.
    resp = client_tx.get(
        "/kpis/routes",
        params={"since": "2999-01-01T00:00:00Z"},
        headers={"X-API-Key": test_api_key},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"auto_approve": 0, "human_review": 0, "reject": 0, "total": 0}


def test_kpis_routes_after_one_match(client_tx, api_session, test_api_key):
    AuditRepository.append(api_session, _entry(Route.AUTO_APPROVE))
    since = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    resp = client_tx.get("/kpis/routes", params={"since": since}, headers={"X-API-Key": test_api_key})
    assert resp.status_code == 200
    body = resp.json()
    assert body["auto_approve"] >= 1
    assert body["total"] == body["auto_approve"] + body["human_review"] + body["reject"]


def test_kpis_recent_limit(client_tx, api_session, test_api_key):
    for _ in range(3):
        AuditRepository.append(api_session, _entry(Route.HUMAN_REVIEW))
    resp = client_tx.get("/kpis/recent", params={"limit": 2}, headers={"X-API-Key": test_api_key})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert all(set(r) == {"run_id", "run_timestamp", "invoice_number", "route", "route_reason", "score", "remark"} for r in body)
