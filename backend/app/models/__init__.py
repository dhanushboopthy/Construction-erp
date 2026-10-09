"""Import every model here so Alembic autogenerate sees the full metadata."""

from app.models.audit import AuditLog
from app.models.auth import AuthSession
from app.models.base import Base
from app.models.masters import Item, ItemUnit, Party, Site
from app.models.numbering import DocumentSequence
from app.models.setup import AppUser, Location, ShopSettings, UserLocation

__all__ = [
    "AppUser",
    "AuditLog",
    "AuthSession",
    "Base",
    "DocumentSequence",
    "Item",
    "ItemUnit",
    "Location",
    "Party",
    "ShopSettings",
    "Site",
    "UserLocation",
]
