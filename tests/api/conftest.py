"""Fixtures for the API tests.

Env vars are set at conftest import time (module-level os.environ.setdefault)
because apmatch.api.config reads the environment at import time and fails
fast; the app module is imported inside fixtures, after this module has run.

DB isolation: the client_tx fixture overrides the app's get_session
dependency with a session bound to a test-owned connection + outer
transaction. A savepoint is opened per request, so the endpoint's
session.commit() releases the savepoint, not the outer transaction —
teardown rolls everything back and the dev audit_log stays clean.
"""

import os

os.environ.setdefault("APMATCH_API_KEY", "test-key-0123456789abcdef")  # 26 chars, test-only
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://apmatch:apmatch_dev_only@localhost:5433/apmatch")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.store.conftest import pg_engine  # noqa: F401  (re-exported; skips if Postgres is down)

API_KEY = os.environ["APMATCH_API_KEY"]


@pytest.fixture(scope="session")
def client():
    from apmatch.api.app import app

    with TestClient(app) as c:  # lifespan builds OCRRouter/LayoutEngine/DB engine once
        yield c


@pytest.fixture(scope="module")
def test_api_key():
    return API_KEY


@pytest.fixture(scope="module")
def api_session(pg_engine):
    connection = pg_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="module")
def client_tx(client, api_session):
    """Client whose DB writes roll back at module teardown."""
    from apmatch.api.app import get_session

    def _override():
        if not api_session.in_nested_transaction():
            api_session.begin_nested()
        yield api_session

    client.app.dependency_overrides[get_session] = _override
    yield client
    client.app.dependency_overrides.pop(get_session, None)
