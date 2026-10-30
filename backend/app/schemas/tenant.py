from pydantic import BaseModel


class TenantOut(BaseModel):
    """What the app shell shows for the business: its name and the line under it."""

    name: str
    tagline: str
    # Where to load the logo from, or none: the app then draws the initials tile.
    logo_url: str | None = None
