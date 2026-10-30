from fastapi import APIRouter

from app.api.deps import DbSession
from app.schemas.tenant import TenantOut
from app.services import shop_settings

router = APIRouter(prefix="/tenant", tags=["tenant"])


@router.get("", response_model=TenantOut)
def get_tenant(db: DbSession) -> TenantOut:
    """Name and tagline only, so the sign-in page and the app shell can show whose shop this is.
    Open to anyone: it is the name printed on every bill, and nothing else from the settings
    (bank details, thresholds) is ever added here."""
    return shop_settings.get_tenant(db)
