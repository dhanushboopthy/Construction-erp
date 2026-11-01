from datetime import datetime
from typing import Literal

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
    # The Duolink subscription (Milestone 21). "read_only" means reading and downloading work
    # and every save is refused with 403 SUBSCRIPTION_EXPIRED.
    access_state: Literal["full", "read_only"] = "full"
    subscription_status: Literal["trial", "active", "expired", "cancelled"] | None = None
    expires_at: datetime | None = None
    days_left: int | None = None
