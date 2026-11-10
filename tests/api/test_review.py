"""Review workflow endpoints: queue, re-check, reviewer decision, case KPIs.

Runs the real FastAPI app against Postgres, but with a light lifespan (no OCR,
no VLM, no embedding model): none of these endpoints reads a document image
with a model. DB writes roll back at the end of the module.
"""

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apmatch.audit.entry import AuditEntry
from apmatch.audit.repository import AuditRepository
from apmatch.scoring.result import Route, RouteReason
from tests.api.conftest import API_KEY

FIXTURES = Path(__file__).resolve().parents[1] / "integration" / "fixtures"
HEADERS = {"X-API-Key": API_KEY}


def _docs(name="happy_path"):
    return {k: json.loads((FIXTURES / name / f"{k}.json").read_text()) for k in ("invoice", "po", "grni", "pard")}


@pytest.fixture(scope="module")
def light_client(pg_engine, api_session, tmp_path_factory):
    from apmatch.api import app as app_module
    from apmatch.api import config
    from apmatch.api.app import app, get_session

    @asynccontextmanager
    async def light_lifespan(a):
        a.state.db_engine = pg_engine
        a.state.embedding_model = None
        yield

    storage = tmp_path_factory.mktemp("storage")
    saved_lifespan, saved_storage = app.router.lifespan_context, config.APMATCH_STORAGE_DIR
    app.router.lifespan_context = light_lifespan
    config.APMATCH_STORAGE_DIR = str(storage)

    def _override():
        if not api_session.in_nested_transaction():
            api_session.begin_nested()
        yield api_session

    app.dependency_overrides[get_session] = _override
    with TestClient(app) as c:
        c.storage = storage  # type: ignore[attr-defined]
        yield c
    app.dependency_overrides.pop(get_session, None)
    app.router.lifespan_context = saved_lifespan
    config.APMATCH_STORAGE_DIR = saved_storage
    assert app_module  # module kept imported for monkeypatch symmetry


def _seed(api_session, storage, *, customer="review_test", route=Route.HUMAN_REVIEW,
          reason=RouteReason.UNREADABLE_FIELD, invoice_number="INV-2026-1123", docs=None, minutes_ago=10):
    run_id = uuid4().hex
    entry = AuditEntry(
        run_id=run_id,
        run_timestamp=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        invoice_number=invoice_number,
        po_number="PO-2026-0451",
        grn_number="GRN-2026-0451",
        pard_ref="PARD-1",
        route=route,
        route_reason=reason,
        score_value=Decimal("0.5000"),
        remark="seeded",
        validation_failures=(),
        match_failures=(),
        input_hash="0" * 64,
        customer_id=customer,
    )
    AuditRepository.append(api_session, entry)
    (storage / "runs").mkdir(parents=True, exist_ok=True)
    (storage / "runs" / f"{run_id}.json").write_text(json.dumps(docs or _docs()))
    (storage / "images").mkdir(parents=True, exist_ok=True)
    (storage / "images" / f"{run_id}_invoice.png").write_bytes(b"\x89PNG fake")
    return run_id


def test_recheck_moves_a_case_out_of_the_queue(light_client, api_session):
    run_id = _seed(api_session, light_client.storage)
    queue = light_client.get("/review-queue?customer_id=review_test", headers=HEADERS).json()
    assert run_id in {r["run_id"] for r in queue}

    r = light_client.post(f"/runs/{run_id}/recheck", json={"documents": _docs()}, headers=HEADERS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["route"] == "AUTO_APPROVE"
    assert body["case_id"] == run_id and body["run_id"] != run_id
    assert body["extraction_source"] == "reviewer"
    assert [h["run_id"] for h in body["history"]] == [run_id, body["run_id"]]
    assert body["extracted"]["invoice"]["invoice_number"] == "INV-2026-1123"

    queue = light_client.get("/review-queue?customer_id=review_test", headers=HEADERS).json()
    assert run_id not in {r["case_id"] for r in queue}

    # The correction shows the case's original scan.
    img = light_client.get(f"/documents/{body['run_id']}/invoice/image", headers=HEADERS)
    assert img.status_code == 200 and img.content.startswith(b"\x89PNG")


def test_recheck_keeps_real_problems_and_explains_them(light_client, api_session):
    run_id = _seed(api_session, light_client.storage, invoice_number="INV-DISC-1")
    docs = _docs("discrepancy_path")
    r = light_client.post(f"/runs/{run_id}/recheck", json={"documents": docs}, headers=HEADERS)
    body = r.json()
    assert body["route"] in ("HUMAN_REVIEW", "REJECT")
    failures = body["validation_failures"] + body["match_failures"]
    assert failures and all(f["message"] for f in failures)


def test_recheck_rejects_unreadable_values(light_client, api_session):
    run_id = _seed(api_session, light_client.storage, invoice_number="INV-BAD-1")
    docs = _docs()
    docs["invoice"]["total"] = "eleven hundred"
    r = light_client.post(f"/runs/{run_id}/recheck", json={"documents": docs}, headers=HEADERS)
    assert r.status_code == 400 and r.json()["error_code"] == "INVALID_DOCUMENT"


def test_duplicate_found_across_cases_not_within_one(light_client, api_session):
    first = _seed(api_session, light_client.storage, customer="dup_test", invoice_number="INV-DUP-9")
    docs = _docs()
    docs["invoice"]["invoice_number"] = "INV-DUP-9"
    docs["pard"]["invoice_number"] = "INV-DUP-9"
    own = light_client.post(f"/runs/{first}/recheck", json={"documents": docs}, headers=HEADERS).json()
    assert "DUPLICATE_INVOICE" not in {f["code"] for f in own["match_failures"]}

    second = _seed(api_session, light_client.storage, customer="dup_test", invoice_number="INV-DUP-9", minutes_ago=1)
    other = light_client.post(f"/runs/{second}/recheck", json={"documents": docs}, headers=HEADERS).json()
    assert "DUPLICATE_INVOICE" in {f["code"] for f in other["match_failures"]}

    # Same number for a different customer is not a duplicate.
    third = _seed(api_session, light_client.storage, customer="other_customer", invoice_number="INV-DUP-9")
    elsewhere = light_client.post(f"/runs/{third}/recheck", json={"documents": docs}, headers=HEADERS).json()
    assert "DUPLICATE_INVOICE" not in {f["code"] for f in elsewhere["match_failures"]}


def test_reviewer_decision_is_recorded_as_a_new_row(light_client, api_session):
    run_id = _seed(api_session, light_client.storage, customer="decide_test", invoice_number="INV-DEC-1")
    r = light_client.post(f"/runs/{run_id}/decision", json={"decision": "approve", "note": "Called supplier, OK"},
                          headers=HEADERS)
    body = r.json()
    assert r.status_code == 200
    assert body["route"] == "AUTO_APPROVE" and body["route_reason"] == "REVIEWER_APPROVED"
    assert body["decided_by"] == "reviewer" and body["case_id"] == run_id
    assert "Called supplier" in body["remark"]
    assert light_client.get(f"/audit/{run_id}", headers=HEADERS).json()["route"] == "HUMAN_REVIEW"  # untouched

    bad = light_client.post(f"/runs/{run_id}/decision", json={"decision": "approve", "note": ""}, headers=HEADERS)
    assert bad.status_code in (400, 422)



def test_a_decided_case_cannot_be_decided_again(light_client, api_session):
    run_id = _seed(api_session, light_client.storage, customer="close_test", invoice_number="INV-CL-1")
    ok = {"decision": "approve", "note": "Checked with supplier"}
    first = light_client.post(f"/runs/{run_id}/decision", json=ok, headers=HEADERS).json()

    # The old step is stale; the new one is final.
    stale = light_client.post(f"/runs/{run_id}/decision", json=ok, headers=HEADERS)
    assert stale.status_code == 409 and stale.json()["error_code"] == "STALE_RUN"
    again = light_client.post(f"/runs/{first['run_id']}/decision", json=ok, headers=HEADERS)
    assert again.status_code == 409 and again.json()["error_code"] == "CASE_CLOSED"
    recheck = light_client.post(f"/runs/{first['run_id']}/recheck", json={"documents": _docs()}, headers=HEADERS)
    assert recheck.status_code == 409 and recheck.json()["error_code"] == "CASE_CLOSED"


def test_a_system_reject_can_still_be_corrected(light_client, api_session):
    run_id = _seed(api_session, light_client.storage, customer="close_test", invoice_number="INV-CL-2",
                   route=Route.REJECT, reason=RouteReason.VALIDATION_BLOCKER)
    r = light_client.post(f"/runs/{run_id}/recheck", json={"documents": _docs()}, headers=HEADERS)
    assert r.status_code == 200, r.text


def test_case_kpis_customers_and_failure_codes(light_client, api_session):
    a = _seed(api_session, light_client.storage, customer="kpi_test", invoice_number="INV-K-1")
    _seed(api_session, light_client.storage, customer="kpi_test", invoice_number="INV-K-2",
          route=Route.REJECT, reason=RouteReason.VALIDATION_BLOCKER)
    light_client.post(f"/runs/{a}/decision", json={"decision": "reject", "note": "wrong vendor"}, headers=HEADERS)
    counts = light_client.get("/kpis/cases?customer_id=kpi_test", headers=HEADERS).json()
    assert counts == {"auto_approve": 0, "human_review": 0, "reject": 2, "total": 2}  # 2 cases, not 3 runs
    assert "kpi_test" in light_client.get("/customers", headers=HEADERS).json()
    codes = light_client.get("/kpis/failure-codes?limit=5", headers=HEADERS)
    assert codes.status_code == 200 and isinstance(codes.json(), list)


def test_unknown_run_is_404(light_client):
    r = light_client.post("/runs/" + "f" * 32 + "/recheck", json={"documents": _docs()}, headers=HEADERS)
    assert r.status_code == 404
