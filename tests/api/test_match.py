"""POST /match — the full pipeline over the real fixture images.

The happy-path POST runs the real OCR pipeline once (module-scoped fixture)
because each document takes tens of seconds; the other tests reuse it or
fail before the pipeline runs.
"""

import re
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT

IMAGES = {
    "invoice": REPO_ROOT / "documents" / "invoice" / "INV_2026_1123.png",
    "po": REPO_ROOT / "documents" / "po" / "PO_2026_0451.png",
    "grni": REPO_ROOT / "documents" / "grni" / "GRN_2026_0322.png",
    "pard": REPO_ROOT / "documents" / "pard" / "PARD_2026_0210.png",
}


@pytest.fixture(scope="module")
def match_body(client_tx, test_api_key):
    files = {name: (p.name, p.read_bytes(), "image/png") for name, p in IMAGES.items()}
    resp = client_tx.post("/match", files=files, headers={"X-API-Key": test_api_key})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_match_happy_path(client_tx, test_api_key, match_body):
    assert match_body["route"] in ("AUTO_APPROVE", "HUMAN_REVIEW")
    assert re.fullmatch(r"[0-9a-f]{32}", match_body["run_id"])
    assert match_body["invoice_number"] == "INV-2026-1123"
    assert match_body["remark"]

    # GET /audit/{run_id} returns the same entry.
    resp = client_tx.get(f"/audit/{match_body['run_id']}", headers={"X-API-Key": test_api_key})
    assert resp.status_code == 200
    audit = resp.json()
    assert audit["run_id"] == match_body["run_id"]
    assert audit["route"] == match_body["route"]
    assert audit["invoice_number"] == "INV-2026-1123"
    assert audit["input_hash"] and len(audit["input_hash"]) == 64


def test_match_missing_invoice_field(client_tx, test_api_key):
    # No invoice file at all -> FastAPI validation error.
    resp = client_tx.post("/match", headers={"X-API-Key": test_api_key})
    assert resp.status_code == 422


def test_match_rejects_oversize_upload(client_tx, test_api_key):
    from apmatch.api import config

    big = b"\x00" * (config.APMATCH_MAX_UPLOAD_BYTES + 1)
    resp = client_tx.post(
        "/match",
        files={"invoice": ("big.png", big, "image/png")},
        headers={"X-API-Key": test_api_key},
    )
    assert resp.status_code in (400, 413)
    assert resp.json()["error_code"] == "UPLOAD_TOO_LARGE"


def test_match_audit_row_written(client_tx, api_session, match_body):
    from sqlalchemy import select

    from apmatch.audit.models import AuditLog

    rows = api_session.execute(select(AuditLog).where(AuditLog.run_id == match_body["run_id"])).scalars().all()
    assert len(rows) == 1
    assert rows[0].route == match_body["route"]
