"""GET /templates — lists the style templates shipped with the image."""


def test_templates_lists_yaml(client, test_api_key):
    resp = client.get("/templates", headers={"X-API-Key": test_api_key})
    assert resp.status_code == 200
    names = resp.json()["templates"]
    assert {"kh.yaml", "us.yaml"} <= set(names)
    assert "in.yaml" not in set(names)  # Indian style removed (D-115)


def test_templates_requires_auth(client):
    resp = client.get("/templates")
    assert resp.status_code == 401
