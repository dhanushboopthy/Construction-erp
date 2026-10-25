from fastapi import APIRouter

from app.api.deps import CurrentTenant, DbSession, OwnerOnly
from app.schemas.platform import TenantPlanOut
from app.schemas.tenancy import TenantPublicOut
from app.services import tenants as tenant_service

router = APIRouter(prefix="/tenant", tags=["auth"])


@router.get("", response_model=TenantPublicOut)
def current_tenant(tenant: CurrentTenant) -> TenantPublicOut:
    """The company this address belongs to, for the sign-in page. 404 TENANT_NOT_FOUND for an
    unknown address; 403 TENANT_SUSPENDED or TENANT_CANCELLED for a closed account."""
    return TenantPublicOut.model_validate(tenant)


@router.get("/plan", response_model=TenantPlanOut)
def plan(_: OwnerOnly, db: DbSession) -> TenantPlanOut:
    """The company's plan and how much of it is in use (Settings, Users)."""
    used = tenant_service.usage(db)
    return TenantPlanOut(
        plan=used.tenant.plan,
        status=used.tenant.status,
        trial_ends_at=used.tenant.trial_ends_at,
        users=used.users,
        max_users=used.limits.max_users,
        locations=used.locations,
        max_locations=used.limits.max_locations,
    )
