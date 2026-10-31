"""Which company (tenant) a database session works for (ADR 0011).

The tenant is read from the request's subdomain and the signed-in user (`api/deps.py`), then
kept on `Session.info`, like the acting user. Services filter every query on
`current_tenant_id(db)`, and PostgreSQL row-level security refuses rows of other companies even
if a filter is forgotten (`app/services/tenancy.py` passes the tenant to the database).
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import func, select
from sqlalchemy.orm import Session

TENANT_KEY = "tenant_id"
PLATFORM_KEY = "platform"


class NoTenantError(RuntimeError):
    """A service ran without a company set on its session: a programming error."""


def set_tenant(db: Session, tenant_id: int) -> None:
    db.info[TENANT_KEY] = tenant_id
    if db.in_transaction():
        # Already inside a transaction: tell the database now. New transactions are told by
        # the after_begin listener.
        db.execute(select(func.set_config("app.tenant_id", str(tenant_id), True)))


@contextmanager
def tenant_context(db: Session, tenant_id: int) -> Iterator[None]:
    """Work as one company for a while, then go back. For a Duolink admin writing a company's
    own rows (Milestone 18): the new rows are stamped with that company, and the session is not
    left pointing at it afterwards."""
    previous = db.info.get(TENANT_KEY)
    set_tenant(db, tenant_id)
    try:
        yield
    finally:
        if previous is None:
            db.info.pop(TENANT_KEY, None)
        else:
            set_tenant(db, int(previous))


def set_platform(db: Session) -> None:
    """A Duolink admin's session (ADR 0012): the database shows rows of every company
    (policy `platform_admin`, migration 0025). Only `api/deps.get_platform_admin` calls this."""
    db.info[PLATFORM_KEY] = True
    if db.in_transaction():
        db.execute(select(func.set_config("app.platform", "on", True)))


def clear_platform(db: Session) -> None:
    """Back to one company's view (a company request never sees other companies' rows)."""
    if db.info.pop(PLATFORM_KEY, None) and db.in_transaction():
        db.execute(select(func.set_config("app.platform", "", True)))


def current_tenant_id(db: Session) -> int:
    tenant_id = db.info.get(TENANT_KEY)
    if tenant_id is None:
        raise NoTenantError("No company is set on this database session")
    return int(tenant_id)
