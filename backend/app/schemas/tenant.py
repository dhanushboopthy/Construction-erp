from pydantic import BaseModel


class TenantOut(BaseModel):
    """What the app shell shows for the business: its name and the line under it."""

    name: str
    tagline: str
