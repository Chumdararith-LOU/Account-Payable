import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://apmatch:apmatch_dev_only@localhost:5433/apmatch"
)

import pytest
from sqlalchemy.orm import Session

from tests.store.conftest import pg_engine  # noqa: F401  (skips if Postgres is down)


@pytest.fixture
def db(pg_engine):  # noqa: F811
    connection = pg_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()
