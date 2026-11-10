"""Password hashing and policy (D-118)."""

import pytest

from apmatch.auth.passwords import (
    DUMMY_HASH,
    WeakPassword,
    check_policy,
    hash_password,
    temporary_password,
    verify_password,
)


def test_hash_verifies_and_is_salted():
    a, b = hash_password("correct horse 1"), hash_password("correct horse 1")
    assert a != b  # random salt
    assert a.startswith("scrypt$")
    assert verify_password("correct horse 1", a) and verify_password("correct horse 1", b)
    assert not verify_password("correct horse 2", a)


def test_verify_rejects_garbage_and_other_schemes():
    assert not verify_password("x", "not-a-hash")
    assert not verify_password("x", "bcrypt$1$2$3$4$5")
    assert not verify_password("anything", DUMMY_HASH)


def test_policy():
    check_policy("ten chars!")
    for bad in ("short", " leading-space-x", "trailing-space ", " " * 12, "x" * 257):
        with pytest.raises(WeakPassword):
            check_policy(bad)


def test_temporary_password_meets_policy():
    pw = temporary_password()
    check_policy(pw)
    assert pw != temporary_password()
