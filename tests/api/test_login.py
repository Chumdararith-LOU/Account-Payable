"""People sign in; machines keep the API key (D-118)."""

from tests.api.conftest import API_KEY, REVIEWER_PASSWORD
from tests.api.test_review import _docs, _seed

KEY = {"X-API-Key": API_KEY}


def _login(client, username, password):
    return client.post("/auth/login", json={"username": username, "password": password})


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_login_me_logout(light_client):
    r = _login(light_client, "Test.Reviewer", REVIEWER_PASSWORD)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["username"] == "test.reviewer" and body["expires_in"] == 12 * 3600
    me = light_client.get("/auth/me", headers=_bearer(body["token"]))
    assert me.json()["display_name"] == "Test Reviewer"
    assert light_client.get("/kpis/cases", headers=_bearer(body["token"])).status_code == 200
    assert light_client.post("/auth/logout", headers=_bearer(body["token"])).status_code == 204
    gone = light_client.get("/kpis/cases", headers=_bearer(body["token"]))
    assert gone.status_code == 401 and gone.json()["error_code"] == "SESSION_INVALID"


def test_wrong_password_is_401_and_says_nothing_specific(light_client):
    for name in ("test.reviewer", "no.such.user"):
        r = _login(light_client, name, "wrong password!")
        assert r.status_code == 401 and r.json()["error_code"] == "LOGIN_INVALID"
        assert r.json()["detail"] == "Wrong username or password"


def test_garbage_bearer_is_rejected(light_client):
    r = light_client.get("/kpis/cases", headers=_bearer("not-a-token"))
    assert r.status_code == 401 and r.json()["error_code"] == "SESSION_INVALID"


def test_machine_key_still_reads_but_cannot_decide(light_client, api_session):
    assert light_client.get("/kpis/cases", headers=KEY).status_code == 200
    run_id = _seed(
        api_session, light_client.storage, customer="login_test", invoice_number="INV-LG-1"
    )
    for path, body in (
        (f"/runs/{run_id}/decision", {"decision": "approve", "note": "x"}),
        (f"/runs/{run_id}/recheck", {"documents": _docs()}),
    ):
        r = light_client.post(path, json=body, headers=KEY)
        assert r.status_code == 403 and r.json()["error_code"] == "USER_REQUIRED"
    assert light_client.get("/users", headers=KEY).json()["error_code"] == "USER_REQUIRED"


def test_admin_creates_user_who_must_change_password(light_client, api_session):
    from apmatch.auth import service as accounts

    accounts.create_user(
        api_session,
        "test.admin",
        "Test Admin",
        "admin password 1",
        role="admin",
        must_change_password=False,
    )
    api_session.flush()
    admin = _bearer(_login(light_client, "test.admin", "admin password 1").json()["token"])

    # Reviewers cannot manage users.
    assert (
        light_client.get("/users", headers=light_client.reviewer_headers).json()["error_code"]
        == "ADMIN_REQUIRED"
    )

    created = light_client.post(
        "/users", json={"username": "new.clerk", "display_name": "New Clerk"}, headers=admin
    )
    assert created.status_code == 201, created.text
    temp = created.json()["temporary_password"]
    assert created.json()["user"]["must_change_password"] is True
    dup = light_client.post(
        "/users", json={"username": "new.clerk", "display_name": "X"}, headers=admin
    )
    assert dup.status_code == 409

    # Until they choose a password, only /auth/me, /auth/password and /auth/logout work.
    clerk = _bearer(_login(light_client, "new.clerk", temp).json()["token"])
    blocked = light_client.get("/kpis/cases", headers=clerk)
    assert blocked.status_code == 403 and blocked.json()["error_code"] == "PASSWORD_CHANGE_REQUIRED"
    assert light_client.get("/auth/me", headers=clerk).json()["must_change_password"] is True

    weak = light_client.post(
        "/auth/password", json={"current_password": temp, "new_password": "short"}, headers=clerk
    )
    assert weak.status_code == 400 and weak.json()["error_code"] == "WEAK_PASSWORD"
    wrong = light_client.post(
        "/auth/password",
        json={"current_password": "nope nope nope", "new_password": "my own password"},
        headers=clerk,
    )
    assert wrong.json()["error_code"] == "PASSWORD_WRONG"
    changed = light_client.post(
        "/auth/password",
        json={"current_password": temp, "new_password": "my own password"},
        headers=clerk,
    )
    assert changed.status_code == 200 and changed.json()["user"]["must_change_password"] is False
    assert light_client.get("/kpis/cases", headers=clerk).status_code == 401  # old session ended
    fresh = _bearer(changed.json()["token"])
    assert light_client.get("/kpis/cases", headers=fresh).status_code == 200

    # Deactivate: their session stops working at once.
    off = light_client.patch("/users/new.clerk", json={"active": False}, headers=admin)
    assert off.status_code == 200 and off.json()["active"] is False
    assert light_client.get("/kpis/cases", headers=fresh).status_code == 401
    # Reset gives a new temporary password.
    reset = light_client.patch(
        "/users/new.clerk", json={"active": True, "reset_password": True}, headers=admin
    )
    assert (
        reset.json()["temporary_password"] and reset.json()["user"]["must_change_password"] is True
    )
    assert (
        light_client.patch("/users/nobody", json={"active": True}, headers=admin).status_code == 404
    )


def test_pdf_upload_errors_are_400(light_client):
    r = light_client.post(
        "/match",
        files={"invoice": ("inv.pdf", b"%PDF-1.4 broken", "application/pdf")},
        headers=light_client.reviewer_headers,
    )
    assert r.status_code == 400 and r.json()["error_code"] == "INVALID_PDF"
