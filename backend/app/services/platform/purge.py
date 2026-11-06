"""The purge switch (Milestone 25, ADR 0013).

Ledgers are append-only and issued documents are permanent (migrations 0003 and 0014). Migration
0038 lets a row go only inside a platform session that has also set `app.data_purge` on. Only
the company restore (here) and M26's data management use this, after a protected backup and a
typed confirmation. The setting is transaction-local, so it ends with the commit or rollback.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.tenancy import PLATFORM_KEY


@contextmanager
def data_purge(db: Session) -> Iterator[None]:
    if not db.info.get(PLATFORM_KEY):
        raise RuntimeError("The purge switch needs a platform session")
    db.execute(select(func.set_config("app.data_purge", "on", True)))
    yield
    # Not reached when the body raises: the caller rolls back, which clears it too.
    db.execute(select(func.set_config("app.data_purge", "", True)))
