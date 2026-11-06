from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.deps import DbSession, PlatformAdminUser, SuperAdminOnly
from app.models.enums import AuditAction, PlatformAction
from app.schemas.common import Page
from app.schemas.platform import OverviewOut, PlatformAuditRow, SignInEvent
from app.schemas.support_access import AdminSessionPage
from app.services.platform import monitoring as service
from app.services.platform import support_access as access_service
from app.services.platform.monitoring import AuditFilters

router = APIRouter(tags=["admin"])

DateFrom = Annotated[date | None, Query(description="first day, India time, included")]
DateTo = Annotated[date | None, Query(description="last day, India time, included")]


@router.get("/overview", response_model=OverviewOut)
def overview(_: PlatformAdminUser, db: DbSession) -> OverviewOut:
    return service.overview(db)


@router.get("/activity", response_model=Page[SignInEvent])
def sign_ins(
    _: PlatformAdminUser,
    db: DbSession,
    tenant_id: int | None = None,
    action: AuditAction | None = None,
    date_from: DateFrom = None,
    date_to: DateTo = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[SignInEvent]:
    """Sign-ins, failed sign-ins and reused tokens across every company, newest first.
    409 DATE_RANGE when `date_to` is before `date_from`."""
    rows, total = service.sign_ins(
        db,
        tenant_id=tenant_id,
        action=action,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return Page[SignInEvent](items=rows, total=total, limit=limit, offset=offset)


@router.get("/audit", response_model=Page[PlatformAuditRow])
def admin_actions(
    _: PlatformAdminUser,
    db: DbSession,
    tenant_id: int | None = None,
    admin_id: int | None = None,
    action: PlatformAction | None = None,
    date_from: DateFrom = None,
    date_to: DateTo = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[PlatformAuditRow]:
    """What Duolink's admins did, newest first, filtered by company, admin, action and dates.
    409 DATE_RANGE when `date_to` is before `date_from`."""
    filters = AuditFilters(tenant_id, admin_id, action, date_from, date_to)
    rows, total = service.admin_actions(db, filters, limit=limit, offset=offset)
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


@router.get(
    "/audit/export",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "The filtered rows as CSV"}},
)
def export_admin_actions(
    admin: SuperAdminOnly,
    db: DbSession,
    tenant_id: int | None = None,
    admin_id: int | None = None,
    action: PlatformAction | None = None,
    date_from: DateFrom = None,
    date_to: DateTo = None,
) -> Response:
    """The same rows as `GET /audit` with the same filters, as CSV, up to 50,000 (Super Admin).
    The export is itself audited (`audit_export`)."""
    filters = AuditFilters(tenant_id, admin_id, action, date_from, date_to)
    body, _ = service.export_admin_actions(db, filters, admin.admin_id)
    return Response(
        body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="duolink-audit.csv"'},
    )
