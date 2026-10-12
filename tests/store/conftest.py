"""Fixtures for the Postgres store tests.

Skips the whole suite if Postgres is unreachable (pg_isready fails). The
session fixture brings the schema to head via ``alembic upgrade head`` and does
NOT drop the DB at teardown (dev convenience). The per-test session fixture
rolls back its transaction so tests are isolated.
"""

import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_URL = "postgresql+psycopg://apmatch:apmatch_dev_only@localhost:5433/apmatch"


def _database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_URL)


def _pg_reachable(url: str) -> bool:
    # TCP probe instead of the pg_isready binary: the binary exists on dev
    # hosts but not inside the api image (server test runs). A listening
    # port is enough for the skip decision; create_engine() is the real test.
    try:
        hostport = url.split("@", 1)[1].split("/", 1)[0]
        host, _, port = hostport.partition(":")
        port = int(port or "5433")
    except (IndexError, ValueError):
        host, port = "localhost", 5433
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def pg_engine():
    url = _database_url()
    if not _pg_reachable(url):
        pytest.skip("Postgres not reachable; run: docker compose up -d postgres", allow_module_level=True)
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env={**os.environ, "DATABASE_URL": url},
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    engine = create_engine(url)
    yield engine
    # Dev convenience: do NOT drop the DB.


@pytest.fixture
def pg_session(pg_engine):
    connection = pg_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()
