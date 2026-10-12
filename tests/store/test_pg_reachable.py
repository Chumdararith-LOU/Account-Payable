"""Tests for the _pg_reachable TCP probe in tests/store/conftest.py."""

import socket

from tests.store.conftest import _pg_reachable


def test_pg_reachable_false_for_closed_port() -> None:
    assert _pg_reachable("postgresql+psycopg://u:p@127.0.0.1:1/db") is False


def test_pg_reachable_true_for_listening_port() -> None:
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        assert _pg_reachable(f"postgresql+psycopg://u:p@127.0.0.1:{port}/db") is True
    finally:
        srv.close()


def test_pg_reachable_malformed_url_falls_back_to_default() -> None:
    # No host:port parseable -> falls back to localhost:5433 (dev default).
    # Whatever that returns, it must not raise.
    _pg_reachable("not-a-url")
