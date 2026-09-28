"""GET /healthz — no auth required."""


def test_healthz_no_auth_required(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_healthz_shape(client):
    body = client.get("/healthz").json()
    assert set(body) == {"status", "version"}
    assert body["status"] == "ok"
    assert isinstance(body["version"], str) and body["version"]
