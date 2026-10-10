"""Profit cuts by brand, shop, user, item and customer (FM8)."""

from datetime import date
from decimal import Decimal
from enum import StrEnum

from app.schemas.common import Schema


class Cut(StrEnum):
    BRAND = "brand"
    SHOP = "shop"
    USER = "user"
    ITEM = "item"
    CUSTOMER = "customer"


class CutRow(Schema):
    key: str
    net_sales: Decimal  # bills less credit notes, excluding GST
    cogs: Decimal
    freight: Decimal
    gross_profit: Decimal  # before stock lost, which belongs to no brand or bill
    margin_pct: Decimal | None
    share_pct: Decimal | None  # of the total gross profit
    tons: Decimal  # sold by weight
    units: Decimal  # sold by the bag, piece or other base unit
    unit_label: str | None  # bag, piece... ("units" when mixed)
    profit_per_ton: Decimal | None  # profit on the lines sold by weight, per ton
    profit_per_unit: Decimal | None  # profit on the other lines, per base unit
    margin_per_base_unit: Decimal | None  # only when every line is in one base unit (kg, bag)


class ProfitabilityOut(Schema):
    period: str
    by: Cut
    date_from: date
    date_to: date
    location_id: int | None
    rows: list[CutRow]
    net_sales: Decimal
    cogs: Decimal
    freight: Decimal
    gross_profit_before_loss: Decimal  # the sum of the rows
    stock_lost: Decimal
    gross_profit: Decimal  # equals the profit and loss gross profit for the month and shop
    tons: Decimal
    profit_per_ton: Decimal | None
    variable_expenses: Decimal
    contribution_per_ton: Decimal | None  # None when some sales were by the bag or piece
    enough_data: bool
    data_note: str | None
