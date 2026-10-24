"""Database engine and session factory (SQLAlchemy 2, sync, psycopg 3)."""

import re
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_settings = get_settings()


def connection_options(app_role: str) -> str:
    """Store and compare timestamps in UTC (the UI converts to Asia/Kolkata), and act as the
    app role so row-level security applies (ADR 0011)."""
    if app_role and not re.fullmatch(r"[a-z_][a-z0-9_]*", app_role):
        raise ValueError("DB_APP_ROLE must be a plain lowercase role name")
    return "-c timezone=UTC" + (f" -c role={app_role}" if app_role else "")


engine = create_engine(
    _settings.database_url,
    pool_size=_settings.db_pool_size,
    max_overflow=_settings.db_max_overflow,
    pool_pre_ping=True,
    connect_args={"options": connection_options(_settings.db_app_role)},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """One session per request. Services commit explicitly; anything uncommitted is rolled back."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
