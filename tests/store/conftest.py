"""Fixtures for the Postgres store tests.

Skips the whole suite if Postgres is unreachable (pg_isready fails). The
session fixture brings the schema to head via ``alembic upgrade head`` and does
NOT drop the DB at teardown (dev convenience). The per-test session fixture
rolls back its transaction so tests are isolated.
"""

import os
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
    try:
        hostport = url.split("@", 1)[1].split("/", 1)[0]
        host, _, port = hostport.partition(":")
    except (IndexError, ValueError):
        host, port = "localhost", "5433"
    port = port or "5433"
    result = subprocess.run(["pg_isready", "-h", host, "-p", port], capture_output=True, text=True)
    return result.returncode == 0


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
