"""Which company (tenant) a database session works for (ADR 0011).

The tenant is read from the request's subdomain and the signed-in user (`api/deps.py`), then
kept on `Session.info`, like the acting user. Services filter every query on
`current_tenant_id(db)`, and PostgreSQL row-level security refuses rows of other companies even
if a filter is forgotten (`app/services/tenancy.py` passes the tenant to the database).
"""

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


def set_platform(db: Session) -> None:
    """A Duolink admin's session (ADR 0012): the database shows rows of every company
    (policy `platform_admin`, migration 0024). Only `api/deps.get_platform_admin` calls this."""
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
