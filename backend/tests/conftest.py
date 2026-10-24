"""Test fixtures.

Unit tests (tests/unit) need nothing. Integration tests (tests/integration) need PostgreSQL:
TEST_DATABASE_URL defaults to postgresql+psycopg://erp:erp@localhost:5432/erp_test.
The schema is built with `alembic upgrade head`, so migrations are tested too. Each test runs
inside a transaction that is rolled back, even when the code under test commits.
"""

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://erp:erp@localhost:5432/erp_test"
)
APP_ROLE = "erp_app"  # created by migration 0023
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("STORAGE_DIR", tempfile.mkdtemp(prefix="erp-files-"))


@pytest.fixture(scope="session")
def engine():
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    eng = create_engine(TEST_DATABASE_URL, connect_args={"options": "-c timezone=UTC"})
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    command.upgrade(cfg, "head")
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine) -> Iterator:
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    from app import services as _services  # noqa: F401 - audit and tenancy listeners

    connection = engine.connect()
    outer = connection.begin()
    # Act as the app does in production: as the role row-level security applies to (ADR 0011).
    connection.execute(text(f"SET ROLE {APP_ROLE}"))
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


@pytest.fixture
def seeded(db):
    from app.scripts.seed import seed

    seed(db, second_shop=True)  # tests keep covering two shops
    return db


@pytest.fixture
def client(seeded) -> Iterator:
    from fastapi.testclient import TestClient

    from app.core.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: seeded
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def login(client, username: str, password: str, host: str | None = None) -> dict[str, str]:
    """Sign in and return the headers for later calls. `host` picks the company by subdomain
    (e.g. "beta.localhost"); without it the default company answers."""
    extra = {"host": host} if host else {}
    response = client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}, headers=extra
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}", **extra}


@contextmanager
def as_db_owner(db) -> Iterator[None]:
    """For the few tests that switch database triggers off: those need the table owner, not the
    app role. Row-level security does not apply inside."""
    from sqlalchemy import text

    db.execute(text("RESET ROLE"))
    try:
        yield
    finally:
        db.execute(text(f"SET ROLE {APP_ROLE}"))
