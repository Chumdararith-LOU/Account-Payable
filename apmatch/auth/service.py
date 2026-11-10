"""Accounts and sessions for people using the review UI (D-118).

Everything here is plain code: no network, no model. The API layer maps the
exceptions to HTTP errors.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from apmatch.auth.models import ROLES, AppUser, UserSession
from apmatch.auth.passwords import DUMMY_HASH, check_policy, hash_password, verify_password

USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,64}$")
SESSION_HOURS = 12


class AuthError(Exception):
    """Base for account errors. ``code`` is the API error code; the message is safe to show."""

    code = "AUTH_ERROR"


class InvalidLogin(AuthError):
    code = "LOGIN_INVALID"


class LoginLocked(AuthError):
    code = "LOGIN_LOCKED"


class UserExists(AuthError):
    code = "USER_EXISTS"


class UserNotFound(AuthError):
    code = "USER_NOT_FOUND"


class InvalidUser(AuthError):
    code = "INVALID_USER"


@dataclass(frozen=True)
class CurrentUser:
    id: int
    username: str
    display_name: str
    role: str
    must_change_password: bool

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def _current(user: AppUser) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        must_change_password=user.must_change_password,
    )


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_username(username: str) -> str:
    return username.strip().lower()


# --- Brute-force guard -------------------------------------------------------


class LoginThrottle:
    """Lock a username for ``lock_seconds`` after ``max_failures`` failures in that window.

    In memory: one API process (uvicorn runs a single worker). A restart clears
    it, which only gives an attacker a few more guesses per restart.
    """

    def __init__(
        self, max_failures: int = 5, lock_seconds: int = 15 * 60, clock=time.monotonic
    ) -> None:
        self.max_failures = max_failures
        self.lock_seconds = lock_seconds
        self._clock = clock
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> list[float]:
        recent = [t for t in self._failures.get(key, []) if now - t < self.lock_seconds]
        self._failures[key] = recent
        return recent

    def check(self, key: str) -> None:
        with self._lock:
            if len(self._recent(key, self._clock())) >= self.max_failures:
                raise LoginLocked("Too many failed sign-ins. Try again in 15 minutes.")

    def failed(self, key: str) -> None:
        with self._lock:
            now = self._clock()
            self._recent(key, now).append(now)

    def succeeded(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


# --- Accounts -----------------------------------------------------------------


def _validate(username: str, display_name: str, role: str) -> None:
    if not USERNAME_RE.fullmatch(username):
        raise InvalidUser(
            "Username: 3-64 characters, lowercase letters, digits, dot, dash or underscore"
        )
    if not display_name.strip() or len(display_name) > 128:
        raise InvalidUser("Display name is required (at most 128 characters)")
    if role not in ROLES:
        raise InvalidUser(f"Role must be one of: {', '.join(ROLES)}")


def get_user(session: Session, username: str) -> AppUser:
    user = session.execute(
        select(AppUser).where(AppUser.username == normalize_username(username))
    ).scalar_one_or_none()
    if user is None:
        raise UserNotFound("No such user")
    return user


def list_users(session: Session) -> list[AppUser]:
    return list(session.execute(select(AppUser).order_by(AppUser.username)).scalars())


def create_user(
    session: Session,
    username: str,
    display_name: str,
    password: str,
    *,
    role: str = "reviewer",
    must_change_password: bool = True,
) -> AppUser:
    username = normalize_username(username)
    _validate(username, display_name, role)
    check_policy(password)
    exists = session.execute(select(AppUser.id).where(AppUser.username == username)).first()
    if exists:
        raise UserExists("That username is taken")
    user = AppUser(
        username=username,
        display_name=display_name.strip(),
        password_hash=hash_password(password),
        role=role,
        active=True,
        must_change_password=must_change_password,
        created_at=datetime.now(UTC),
    )
    session.add(user)
    session.flush()
    return user


def end_sessions(session: Session, user_id: int) -> None:
    session.execute(delete(UserSession).where(UserSession.user_id == user_id))


def set_password(session: Session, user: AppUser, password: str, *, must_change: bool) -> None:
    check_policy(password)
    user.password_hash = hash_password(password)
    user.must_change_password = must_change
    end_sessions(session, user.id)  # a new password signs out every device


def update_user(
    session: Session,
    user: AppUser,
    *,
    display_name: str | None = None,
    role: str | None = None,
    active: bool | None = None,
) -> None:
    new_name = display_name if display_name is not None else user.display_name
    new_role = role if role is not None else user.role
    _validate(user.username, new_name, new_role)
    if (role is not None and role != "admin") or active is False:
        _keep_one_admin(session, user)
    user.display_name = new_name.strip()
    user.role = new_role
    if active is not None:
        user.active = active
        if not active:
            end_sessions(session, user.id)


def _keep_one_admin(session: Session, user: AppUser) -> None:
    if user.role != "admin" or not user.active:
        return
    others = session.execute(
        select(AppUser.id).where(
            AppUser.role == "admin", AppUser.active.is_(True), AppUser.id != user.id
        )
    ).first()
    if not others:
        raise InvalidUser("At least one active admin must remain")


# --- Sessions -----------------------------------------------------------------


def login(
    session: Session, username: str, password: str, throttle: LoginThrottle
) -> tuple[str, CurrentUser]:
    key = normalize_username(username)
    throttle.check(key)
    user = session.execute(select(AppUser).where(AppUser.username == key)).scalar_one_or_none()
    ok = verify_password(password, user.password_hash if user else DUMMY_HASH)
    if not ok or user is None or not user.active:
        throttle.failed(key)
        raise InvalidLogin("Wrong username or password")
    throttle.succeeded(key)
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    session.add(
        UserSession(
            token_hash=token_hash(token),
            user_id=user.id,
            created_at=now,
            expires_at=now + timedelta(hours=SESSION_HOURS),
        )
    )
    session.execute(
        delete(UserSession).where(UserSession.user_id == user.id, UserSession.expires_at < now)
    )
    return token, _current(user)


def user_for_token(session: Session, token: str) -> CurrentUser | None:
    """The signed-in user for a session token, or None if unknown, expired or deactivated."""
    row = session.execute(
        select(AppUser, UserSession.expires_at)
        .join(UserSession, UserSession.user_id == AppUser.id)
        .where(UserSession.token_hash == token_hash(token))
    ).first()
    if row is None:
        return None
    user, expires_at = row
    if expires_at <= datetime.now(UTC) or not user.active:
        return None
    return _current(user)


def logout(session: Session, token: str) -> None:
    session.execute(delete(UserSession).where(UserSession.token_hash == token_hash(token)))
