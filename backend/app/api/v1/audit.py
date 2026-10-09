from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import DbSession, OwnerOnly
from app.core.tenancy import TENANT_ID
from app.models.audit import AuditLog
from app.models.enums import AuditAction
from app.schemas.audit import AuditLogOut
from app.schemas.common import Page

router = APIRouter(prefix="/audit-log", tags=["audit"])


@router.get("", response_model=Page[AuditLogOut])
def list_audit_log(
    _: OwnerOnly,
    db: DbSession,
    entity: str | None = None,
    entity_id: str | None = None,
    user_id: int | None = None,
    action: AuditAction | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[AuditLogOut]:
    filters = [AuditLog.tenant_id == TENANT_ID]
    if entity:
        filters.append(AuditLog.entity == entity)
    if entity_id:
        filters.append(AuditLog.entity_id == entity_id)
    if user_id is not None:
        filters.append(AuditLog.user_id == user_id)
    if action:
        filters.append(AuditLog.action == action)
    if since:
        filters.append(AuditLog.at >= since)
    if until:
        filters.append(AuditLog.at < until)

    total = db.execute(select(func.count()).select_from(AuditLog).where(*filters)).scalar_one()
    rows = db.execute(
        select(AuditLog).where(*filters).order_by(AuditLog.id.desc()).limit(limit).offset(offset)
    ).scalars()
    return Page[AuditLogOut](
        items=[AuditLogOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )
