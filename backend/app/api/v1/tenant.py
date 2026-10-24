from fastapi import APIRouter

from app.api.deps import CurrentTenant
from app.schemas.tenancy import TenantPublicOut

router = APIRouter(prefix="/tenant", tags=["auth"])


@router.get("", response_model=TenantPublicOut)
def current_tenant(tenant: CurrentTenant) -> TenantPublicOut:
    """The company this address belongs to, for the sign-in page. 404 TENANT_NOT_FOUND for an
    unknown address; 403 TENANT_SUSPENDED or TENANT_CANCELLED for a closed account."""
    return TenantPublicOut.model_validate(tenant)
