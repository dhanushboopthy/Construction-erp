"""Import every model here so Alembic autogenerate sees the full metadata."""

from app.models.audit import AuditLog
from app.models.auth import AuthSession
from app.models.base import Base
from app.models.ledgers import PartyLedger, StockLedger
from app.models.masters import Item, ItemUnit, Party, Site
from app.models.numbering import DocumentSequence
from app.models.opening import OpeningBalance
from app.models.purchasing import CostComponent, Payment, Purchase, PurchaseCost, PurchaseLine
from app.models.rates import CustomerRate, ItemMargin, MarketRate
from app.models.setup import AppUser, Location, ShopSettings, UserLocation
from app.models.stock_ops import StockCount, StockCountLine, StockTransfer, StockTransferLine

__all__ = [
    "AppUser",
    "AuditLog",
    "AuthSession",
    "Base",
    "CostComponent",
    "CustomerRate",
    "DocumentSequence",
    "Item",
    "ItemMargin",
    "ItemUnit",
    "Location",
    "MarketRate",
    "OpeningBalance",
    "Party",
    "PartyLedger",
    "Payment",
    "Purchase",
    "PurchaseCost",
    "PurchaseLine",
    "ShopSettings",
    "Site",
    "StockCount",
    "StockCountLine",
    "StockLedger",
    "StockTransfer",
    "StockTransferLine",
    "UserLocation",
]
