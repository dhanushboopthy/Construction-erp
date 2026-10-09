"""Import every model here so Alembic autogenerate sees the full metadata."""

from app.models.approvals import Approval
from app.models.audit import AuditLog
from app.models.auth import AuthSession
from app.models.base import Base
from app.models.compliance import EInvoice, EwayBill
from app.models.documents import Attachment
from app.models.ledgers import PartyLedger, StockLedger
from app.models.masters import Item, ItemUnit, Party, Site
from app.models.numbering import DocumentSequence
from app.models.opening import OpeningBalance
from app.models.purchasing import CostComponent, Payment, Purchase, PurchaseCost, PurchaseLine
from app.models.rates import CustomerRate, ItemMargin, MarketRate
from app.models.returns import CreditNote, CreditNoteLine, DebitNote, DebitNoteLine
from app.models.sales import SalesInvoice, SalesLine
from app.models.schemes import SupplierScheme
from app.models.setup import AppUser, Location, ShopSettings, UserLocation
from app.models.stock_ops import StockCount, StockCountLine, StockTransfer, StockTransferLine
from app.models.transport import DropShipLink, Trip, Vehicle

__all__ = [
    "AppUser",
    "Approval",
    "Attachment",
    "AuditLog",
    "AuthSession",
    "Base",
    "CostComponent",
    "CreditNote",
    "CreditNoteLine",
    "CustomerRate",
    "DebitNote",
    "DebitNoteLine",
    "DocumentSequence",
    "DropShipLink",
    "EInvoice",
    "EwayBill",
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
    "SalesInvoice",
    "SalesLine",
    "ShopSettings",
    "Site",
    "StockCount",
    "StockCountLine",
    "StockLedger",
    "StockTransfer",
    "StockTransferLine",
    "SupplierScheme",
    "Trip",
    "UserLocation",
    "Vehicle",
]
