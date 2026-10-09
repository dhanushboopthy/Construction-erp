from decimal import Decimal

from app.models.enums import ItemCategory
from app.schemas.common import Schema


class StockLocationOut(Schema):
    location_id: int
    code: str
    name: str
    quantity: Decimal


class StockItemOut(Schema):
    """Availability for everyone: quantities only, no cost (rule B4)."""

    item_id: int
    name: str
    category: ItemCategory
    base_unit: str
    quantity: Decimal
    locations: list[StockLocationOut]


class StockItemOwnerOut(StockItemOut):
    avg_cost: Decimal
    value: Decimal
