from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession, PlatformAdminUser
from app.models.enums import AuditAction, PlatformAction
from app.schemas.common import Page
from app.schemas.platform import OverviewOut, PlatformAuditRow, SignInEvent
from app.schemas.support_access import AdminSessionPage
from app.services.platform import monitoring as service
from app.services.platform import support_access as access_service

router = APIRouter(tags=["admin"])


@router.get("/overview", response_model=OverviewOut)
def overview(_: PlatformAdminUser, db: DbSession) -> OverviewOut:
    return service.overview(db)


@router.get("/activity", response_model=Page[SignInEvent])
def sign_ins(
    _: PlatformAdminUser,
    db: DbSession,
    tenant_id: int | None = None,
    action: AuditAction | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[SignInEvent]:
    """Sign-ins, failed sign-ins and reused tokens across every company, newest first."""
    rows, total = service.sign_ins(
        db, tenant_id=tenant_id, action=action, limit=limit, offset=offset
    )
    return Page[SignInEvent](items=rows, total=total, limit=limit, offset=offset)


@router.get("/audit", response_model=Page[PlatformAuditRow])
def admin_actions(
    _: PlatformAdminUser,
    db: DbSession,
    tenant_id: int | None = None,
    action: PlatformAction | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[PlatformAuditRow]:
    """What Duolink's admins did, newest first."""
    rows, total = service.admin_actions(
        db, tenant_id=tenant_id, action=action, limit=limit, offset=offset
    )
    return Page[PlatformAuditRow](items=rows, total=total, limit=limit, offset=offset)


@router.get("/audit/support-sessions", response_model=AdminSessionPage)
def support_sessions(
    _: PlatformAdminUser,
    db: DbSession,
    tenant_id: int | None = None,
    admin_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminSessionPage:
    """Company access (M23): every support session at every company, newest first, with its
    request count. `stale` counts sessions never ended whose token has expired."""
    return access_service.list_sessions(
        db, tenant_id=tenant_id, admin_id=admin_id, limit=limit, offset=offset
    )
