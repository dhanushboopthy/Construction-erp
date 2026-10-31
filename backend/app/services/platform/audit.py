"""The platform audit log: one row per admin sign-in and per change an admin makes."""

from typing import Any

from sqlalchemy.orm import Session

from app.core.context import client_ip_var, request_id_var
from app.models.enums import PlatformAction
from app.models.platform import PlatformAuditLog
from app.services.audit import _jsonable


def record(
    db: Session,
    action: PlatformAction,
    admin_id: int | None,
    *,
    tenant_id: int | None = None,
    target_user_id: int | None = None,
    target_admin_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Add the row to the session; it is saved with the caller's commit."""
    db.add(
        PlatformAuditLog(
            admin_id=admin_id,
            action=action,
            tenant_id=tenant_id,
            target_user_id=target_user_id,
            target_admin_id=target_admin_id,
            details={k: _jsonable(v) for k, v in (details or {}).items()},
            request_id=request_id_var.get(),
            ip=client_ip_var.get(),
        )
    )
