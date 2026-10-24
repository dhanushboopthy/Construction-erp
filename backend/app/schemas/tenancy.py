from app.models.enums import TenantStatus
from app.schemas.common import Schema


class TenantPublicOut(Schema):
    """What the sign-in page may show before anyone signs in."""

    slug: str
    name: str
    status: TenantStatus
