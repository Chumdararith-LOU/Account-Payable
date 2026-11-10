"""Accounts, sign-in, sessions and the brute-force guard (D-118)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from apmatch.auth import service as accounts
from apmatch.auth.__main__ import main as cli_main
from apmatch.auth.models import UserSession
from apmatch.auth.passwords import WeakPassword

PW = "a good password"


def _throttle():
    return accounts.LoginThrottle()


def test_create_and_login(db):
    accounts.create_user(db, "Sokha.Chan", "Sokha Chan", PW)
    token, user = accounts.login(db, "  sokha.chan ", PW, _throttle())
    assert user.username == "sokha.chan" and user.role == "reviewer" and user.must_change_password
    assert accounts.user_for_token(db, token).username == "sokha.chan"
    assert accounts.user_for_token(db, token + "x") is None
    accounts.logout(db, token)
    assert accounts.user_for_token(db, token) is None


def test_only_the_token_hash_is_stored(db):
    accounts.create_user(db, "hash.check", "H", PW)
    token, _ = accounts.login(db, "hash.check", PW, _throttle())
    stored = db.query(UserSession.token_hash).all()
    assert (accounts.token_hash(token),) in stored and all(token not in row[0] for row in stored)


def test_wrong_password_unknown_user_and_inactive_look_the_same(db):
    user = accounts.create_user(db, "dara", "Dara", PW)
    throttle = _throttle()
    for name, pw in (("dara", "wrong password"), ("nobody", PW)):
        with pytest.raises(accounts.InvalidLogin):
            accounts.login(db, name, pw, throttle)
    accounts.create_user(db, "admin1", "Admin", PW, role="admin")
    accounts.update_user(db, user, active=False)
    with pytest.raises(accounts.InvalidLogin):
        accounts.login(db, "dara", PW, throttle)


def test_lockout_after_five_failures(db):
    accounts.create_user(db, "lock.me", "L", PW)
    now = [1000.0]
    throttle = accounts.LoginThrottle(clock=lambda: now[0])
    for _ in range(5):
        with pytest.raises(accounts.InvalidLogin):
            accounts.login(db, "lock.me", "wrong password", throttle)
    with pytest.raises(accounts.LoginLocked):
        accounts.login(db, "lock.me", PW, throttle)  # even the right password
    now[0] += 15 * 60 + 1
    accounts.login(db, "lock.me", PW, throttle)


def test_expired_session_is_rejected(db):
    accounts.create_user(db, "expire.me", "E", PW)
    token, _ = accounts.login(db, "expire.me", PW, _throttle())
    db.execute(
        update(UserSession)
        .where(UserSession.token_hash == accounts.token_hash(token))
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    assert accounts.user_for_token(db, token) is None


def test_new_password_or_deactivation_ends_sessions(db):
    accounts.create_user(db, "boss", "Boss", PW, role="admin")
    user = accounts.create_user(db, "clerk", "Clerk", PW)
    token, _ = accounts.login(db, "clerk", PW, _throttle())
    accounts.set_password(db, user, "another good one", must_change=False)
    assert accounts.user_for_token(db, token) is None
    token, current = accounts.login(db, "clerk", "another good one", _throttle())
    assert not current.must_change_password
    accounts.update_user(db, user, active=False)
    assert accounts.user_for_token(db, token) is None


def test_validation(db):
    accounts.create_user(db, "taken", "T", PW)
    with pytest.raises(accounts.UserExists):
        accounts.create_user(db, "TAKEN", "T2", PW)
    with pytest.raises(accounts.InvalidUser):
        accounts.create_user(db, "a b", "Bad", PW)
    with pytest.raises(accounts.InvalidUser):
        accounts.create_user(db, "rolebad", "R", PW, role="owner")
    with pytest.raises(WeakPassword):
        accounts.create_user(db, "weak", "W", "short")


def test_last_admin_cannot_be_removed(db):
    # The test DB may hold admins from other runs; give this test its own world.
    for u in accounts.list_users(db):
        u.active = False
    db.flush()
    admin = accounts.create_user(db, "only.admin", "Only", PW, role="admin")
    with pytest.raises(accounts.InvalidUser):
        accounts.update_user(db, admin, role="reviewer")
    with pytest.raises(accounts.InvalidUser):
        accounts.update_user(db, admin, active=False)
    accounts.create_user(db, "second.admin", "Second", PW, role="admin")
    accounts.update_user(db, admin, role="reviewer")


def test_cli_creates_user_with_temporary_password(pg_engine, capsys, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", str(pg_engine.url.render_as_string(hide_password=False)))
    name = "cli.user." + datetime.now(UTC).strftime("%H%M%S%f")
    assert cli_main(["create-user", name, "CLI User"]) == 0
    out = capsys.readouterr().out
    assert f"user: {name} (reviewer)" in out and "temporary password: " in out
    assert cli_main(["create-user", name, "Again"]) == 1  # taken
    assert cli_main(["reset-password", name]) == 0
