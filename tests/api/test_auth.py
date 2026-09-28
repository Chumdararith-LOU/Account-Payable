"""Auth: every endpoint except /healthz requires a valid X-API-Key."""


def test_match_requires_api_key(client):
    resp = client.post("/match", files={"invoice": ("inv.png", b"fake", "image/png")})
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "AUTH_MISSING"


def test_match_rejects_wrong_api_key(client):
    resp = client.post(
        "/match",
        files={"invoice": ("inv.png", b"fake", "image/png")},
        headers={"X-API-Key": "wrong-key-0123456789abcdef"},
    )
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "AUTH_INVALID"


def test_audit_requires_api_key(client):
    resp = client.get("/audit/" + "0" * 32)
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "AUTH_MISSING"


def test_kpis_requires_api_key(client):
    assert client.get("/kpis/routes").json()["error_code"] == "AUTH_MISSING"
    assert client.get("/kpis/recent").json()["error_code"] == "AUTH_MISSING"
