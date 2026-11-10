"""Password hashing with the standard library's scrypt (no extra dependency).

Stored format: ``scrypt$<n>$<r>$<p>$<salt b64>$<hash b64>``. The parameters
travel with the hash, so they can be raised later without breaking old
passwords (verify reads them from the stored string).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_N, _R, _P = 2**14, 8, 1
_DKLEN = 32
MIN_LENGTH = 10
MAX_LENGTH = 256


class WeakPassword(ValueError):
    """The password does not meet the policy (message is safe to show)."""


def check_policy(password: str) -> None:
    if len(password) < MIN_LENGTH:
        raise WeakPassword(f"Password must be at least {MIN_LENGTH} characters")
    if len(password) > MAX_LENGTH:
        raise WeakPassword(f"Password must be at most {MAX_LENGTH} characters")
    if password.strip() != password or not password.strip():
        raise WeakPassword("Password must not start or end with spaces")


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(hash_b64)
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=base64.b64decode(salt_b64),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected)


# Verified against when the username does not exist, so a wrong username
# takes as long as a wrong password (no user enumeration by timing).
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def temporary_password() -> str:
    """A random password for a new account; the user must change it at first login."""
    return secrets.token_urlsafe(12)
