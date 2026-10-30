"""Session listeners that keep every company's rows apart (ADR 0011).

- before_flush: a new row gets the session's company; a row for another company is refused.
- after_begin: each transaction tells PostgreSQL the company (`app.tenant_id`), which the
  row-level security policies of migration 0024 compare with every row read or written, and
  whether this is a Duolink admin's session (`app.platform`, migration 0025).
"""

from sqlalchemy import Connection, event, func, select
from sqlalchemy.orm import Session, SessionTransaction, UOWTransaction

from app.core.tenancy import PLATFORM_KEY, TENANT_KEY, NoTenantError
from app.models.base import TenantMixin


class CrossTenantWriteError(RuntimeError):
    """A row for one company was added on a session working for another."""


@event.listens_for(Session, "before_flush")
def _stamp_tenant(session: Session, _ctx: UOWTransaction, _instances: object) -> None:
    tenant_id = session.info.get(TENANT_KEY)
    for obj in session.new:
        if not isinstance(obj, TenantMixin):
            continue
        if obj.tenant_id is None:
            if tenant_id is None:
                raise NoTenantError(f"No company is set to save {type(obj).__name__}")
            obj.tenant_id = tenant_id
        elif tenant_id is not None and obj.tenant_id != tenant_id:
            raise CrossTenantWriteError(
                f"{type(obj).__name__} belongs to company {obj.tenant_id}, "
                f"but this session works for company {tenant_id}"
            )


@event.listens_for(Session, "after_begin")
def _tell_database(session: Session, _tx: SessionTransaction, connection: Connection) -> None:
    tenant_id = session.info.get(TENANT_KEY)
    if tenant_id is not None:
        connection.execute(select(func.set_config("app.tenant_id", str(tenant_id), True)))
    if session.info.get(PLATFORM_KEY):
        connection.execute(select(func.set_config("app.platform", "on", True)))
