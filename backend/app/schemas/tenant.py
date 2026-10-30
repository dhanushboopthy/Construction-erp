from pydantic import BaseModel

from app.models.enums import TenantStatus


class TenantOut(BaseModel):
    """What the sign-in page and the app shell show for the company at this address: which
    company (ADR 0011), its business name and the line under it."""

    slug: str
    status: TenantStatus
    name: str
    tagline: str
    # Where to load the logo from, or none: the app then draws the initials tile.
    logo_url: str | None = None
