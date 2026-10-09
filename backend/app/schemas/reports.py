from datetime import date
from decimal import Decimal
from enum import StrEnum

from app.schemas.common import Schema


class TodayOut(Schema):
    as_of: date
    items_in_stock: int
    customers_owe: Decimal
    we_owe: Decimal | None  # not for counter staff
    sales_today: Decimal
    returns_today: Decimal
    profit_today: Decimal | None  # owner only


class ProfitGroup(StrEnum):
    ITEM = "item"
    CUSTOMER = "customer"
    SITE = "site"


class ProfitRow(Schema):
    key: str
    taxable: Decimal  # sales less returns, excluding GST
    cost: Decimal
    freight: Decimal
    profit: Decimal
    margin_pct: Decimal | None


class ProfitReport(Schema):
    group: ProfitGroup
    date_from: date
    date_to: date
    rows: list[ProfitRow]
    taxable: Decimal
    cost: Decimal
    freight: Decimal
    profit: Decimal


class SegmentMonth(Schema):
    month: str  # 2026-04
    retail: Decimal
    contractor: Decimal
    bulk: Decimal
    unassigned: Decimal
    total: Decimal


class SegmentReport(Schema):
    financial_year: str
    start_year: int
    months: list[SegmentMonth]
    total: Decimal
