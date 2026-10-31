"""CORS: the browser frontend (frontend/index.html) calls the API cross-origin."""

ORIGIN = "http://localhost:3000"


def test_preflight_allows_custom_header(client):
    resp = client.options(
        "/match",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-api-key",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] in ("*", ORIGIN)
    assert "x-api-key" in resp.headers.get("access-control-allow-headers", "").lower()


def test_simple_request_gets_cors_header(client):
    resp = client.get("/healthz", headers={"Origin": ORIGIN})
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] in ("*", ORIGIN)
