"""GET /documents/{run_id}/{name}/image + extracted sidecar (review UI).

The module-scoped match_body fixture runs the real OCR pipeline once (same
pattern as test_match.py); the 404/auth tests fail before any pipeline work.
"""

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


def test_invoice_image_served(client_tx, test_api_key, match_body):
    rid = match_body["run_id"]
    resp = client_tx.get(f"/documents/{rid}/invoice/image", headers={"X-API-Key": test_api_key})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/")
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic — the original bytes


def test_po_image_served(client_tx, test_api_key, match_body):
    rid = match_body["run_id"]
    resp = client_tx.get(f"/documents/{rid}/po/image", headers={"X-API-Key": test_api_key})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/")


def test_missing_run_404(client_tx, test_api_key):
    resp = client_tx.get("/documents/" + "0" * 32 + "/invoice/image", headers={"X-API-Key": test_api_key})
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "DOCUMENT_NOT_FOUND"


def test_bad_run_id_404(client_tx, test_api_key):
    resp = client_tx.get("/documents/not-a-hex-run-id/invoice/image", headers={"X-API-Key": test_api_key})
    assert resp.status_code == 404


def test_bad_doc_name_404(client_tx, test_api_key, match_body):
    resp = client_tx.get(f"/documents/{match_body['run_id']}/bogus/image", headers={"X-API-Key": test_api_key})
    assert resp.status_code == 404


def test_image_requires_auth(client_tx, match_body):
    resp = client_tx.get(f"/documents/{match_body['run_id']}/invoice/image")
    assert resp.status_code == 401


def test_audit_includes_extracted_documents(client_tx, test_api_key, match_body):
    audit = client_tx.get(f"/audit/{match_body['run_id']}", headers={"X-API-Key": test_api_key}).json()
    assert audit["extracted"]["invoice"]["invoice_number"] == "INV-2026-1123"
    assert audit["extracted"]["po"] is not None
    assert audit["extracted"]["grni"] is not None
    assert audit["extracted"]["pard"] is not None
