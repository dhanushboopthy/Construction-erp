from fastapi import APIRouter

from app.api.deps import CurrentPrincipal, DbSession
from app.schemas.tenant import TenantOut
from app.services import shop_settings

router = APIRouter(prefix="/tenant", tags=["tenant"])


@router.get("", response_model=TenantOut)
def get_tenant(_: CurrentPrincipal, db: DbSession) -> TenantOut:
    """Name and tagline only, so the shell can brand itself without reading the shop settings
    (bank details, thresholds) that counter staff have no use for."""
    return shop_settings.get_tenant(db)
