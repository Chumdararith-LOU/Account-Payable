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


def test_match_response_includes_similarity_matches_field(client_tx, test_api_key, match_body):
    assert "similarity_matches" in match_body
    assert isinstance(match_body["similarity_matches"], list)
    # The current fixtures match exactly — the similarity fallback never fires.
    assert match_body["similarity_matches"] == []


def test_audit_response_includes_similarity_matches_field(client_tx, test_api_key, match_body):
    resp = client_tx.get(f"/audit/{match_body['run_id']}", headers={"X-API-Key": test_api_key})
    assert resp.status_code == 200
    audit = resp.json()
    assert "similarity_matches" in audit
    assert isinstance(audit["similarity_matches"], list)
    assert audit["similarity_matches"] == []


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


def test_match_rejects_malformed_image(client_tx, test_api_key):
    # An 8-byte PNG signature with no IHDR chunk is not a decodable image.
    bad = b"\x89PNG\r\n\x1a\n"
    files = {name: (f"{name}.png", bad, "image/png") for name in ("invoice", "po", "grni", "pard")}
    resp = client_tx.post("/match", files=files, headers={"X-API-Key": test_api_key})
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "INVALID_IMAGE"


def test_match_audit_row_written(client_tx, api_session, match_body):
    from sqlalchemy import select

    from apmatch.audit.models import AuditLog

    rows = api_session.execute(select(AuditLog).where(AuditLog.run_id == match_body["run_id"])).scalars().all()
    assert len(rows) == 1
    assert rows[0].route == match_body["route"]


def test_match_default_customer_id(client_tx, test_api_key, match_body):
    # The module-scoped POST was sent without a customer_id.
    assert match_body["customer_id"] == "default"


def test_match_with_customer_id(client_tx, test_api_key):
    files = {name: (p.name, p.read_bytes(), "image/png") for name, p in IMAGES.items()}
    resp = client_tx.post(
        "/match",
        files=files,
        params={"customer_id": "hotel_acme"},
        headers={"X-API-Key": test_api_key},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["customer_id"] == "hotel_acme"


def test_match_rejects_invalid_customer_id(client_tx, test_api_key):
    # Uppercase is invalid — the tag must be lowercase. Rejected before any
    # pipeline work (a bad tag must not cost an OCR run).
    files = {"invoice": ("invoice.png", b"\x89PNG\r\n\x1a\n", "image/png")}
    resp = client_tx.post(
        "/match",
        files=files,
        params={"customer_id": "Hotel-ACME"},
        headers={"X-API-Key": test_api_key},
    )
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "INVALID_CUSTOMER_ID"


def test_match_rejects_overlong_customer_id(client_tx, test_api_key):
    files = {"invoice": ("invoice.png", b"\x89PNG\r\n\x1a\n", "image/png")}
    resp = client_tx.post(
        "/match",
        files=files,
        params={"customer_id": "a" * 65},
        headers={"X-API-Key": test_api_key},
    )
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "INVALID_CUSTOMER_ID"
