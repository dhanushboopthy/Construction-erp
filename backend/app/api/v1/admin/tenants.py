from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DbSession, PlatformAdminUser
from app.models.enums import TenantPlan, TenantStatus
from app.schemas.common import Page
from app.schemas.platform import SuspendRequest, TenantCreate, TenantDetail, TenantRow, TenantUpdate
from app.services.platform import tenants as service

router = APIRouter(prefix="/tenants", tags=["admin"])


@router.get("", response_model=Page[TenantRow])
def list_tenants(
    _: PlatformAdminUser,
    db: DbSession,
    q: str | None = None,
    status: TenantStatus | None = None,
    plan: TenantPlan | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[TenantRow]:
    rows, total = service.list_tenants(
        db, q=q, status=status, plan=plan, limit=limit, offset=offset
    )
    return Page[TenantRow](items=rows, total=total, limit=limit, offset=offset)


@router.post("", response_model=TenantDetail, status_code=status.HTTP_201_CREATED)
def create_tenant(body: TenantCreate, admin: PlatformAdminUser, db: DbSession) -> TenantDetail:
    """A new company with starter data and its first owner, who signs in at <slug>.<domain>."""
    tenant = service.create_tenant(db, body, admin.admin_id)
    return service.detail(db, tenant.id)


@router.get("/{tenant_id}", response_model=TenantDetail)
def get_tenant(tenant_id: int, _: PlatformAdminUser, db: DbSession) -> TenantDetail:
    return service.detail(db, tenant_id)


@router.patch("/{tenant_id}", response_model=TenantDetail)
def update_tenant(
    tenant_id: int, body: TenantUpdate, admin: PlatformAdminUser, db: DbSession
) -> TenantDetail:
    service.update_tenant(db, tenant_id, body, admin.admin_id)
    return service.detail(db, tenant_id)


@router.post("/{tenant_id}/suspend", response_model=TenantDetail)
def suspend(
    tenant_id: int, body: SuspendRequest, admin: PlatformAdminUser, db: DbSession
) -> TenantDetail:
    """Everyone at the company is signed out and cannot sign in until reactivated."""
    service.suspend(db, tenant_id, body.reason, admin.admin_id)
    return service.detail(db, tenant_id)


@router.post("/{tenant_id}/reactivate", response_model=TenantDetail)
def reactivate(tenant_id: int, admin: PlatformAdminUser, db: DbSession) -> TenantDetail:
    service.reactivate(db, tenant_id, admin.admin_id)
    return service.detail(db, tenant_id)
