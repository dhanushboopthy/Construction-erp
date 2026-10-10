"""Inventory analytics, replenishment, stock value (NRV) and weight shortages (FM6)."""

from datetime import date
from decimal import Decimal

from pydantic import Field

from app.models.enums import ItemCategory
from app.schemas.common import Schema


class InventoryRowOut(Schema):
    item_id: int
    item_name: str
    category: ItemCategory
    base_unit: str
    on_hand: Decimal
    avg_cost: Decimal
    value: Decimal
    last_movement: (
        date | None
    )  # last purchase, sale or return: adjustments and write-downs do not count
    age_days: int | None
    age_bucket: str | None
    days_sold: int  # days in the last 90 on which it sold
    consumption: Decimal  # cost of what was sold in the last 90 days
    abc: str | None  # A, B or C; blank when there is too little history or nothing sold
    fsn: str | None  # F, S or N; blank when there is too little history
    avg_daily_sales: Decimal | None  # last 30 days
    cover_days: Decimal | None
    lead_days: int
    safety_days: int
    reorder_point: Decimal | None
    short_by: Decimal | None
    reorder_now: bool


class AgeBucketOut(Schema):
    bucket: str
    value: Decimal
    items: int


class InventoryAnalyticsOut(Schema):
    as_of: date
    history_days: int
    enough_data: bool
    data_note: str | None
    default_lead_days: int
    default_safety_days: int
    fsn_fast_min_days: int
    stock_value: Decimal
    dead_stock_value: Decimal  # last movement over 180 days ago
    aging: list[AgeBucketOut]
    rows: list[InventoryRowOut]


class NrvRowOut(Schema):
    item_id: int
    item_name: str
    base_unit: str
    on_hand: Decimal
    avg_cost: Decimal
    value: Decimal
    market_rate: Decimal | None  # today's rate per base unit; None when no rate is set
    market_date: date | None
    nrv: Decimal | None
    nrv_loss: Decimal
    replacement_cost: Decimal | None  # the last purchase, landed, per base unit
    holding_gain_loss: Decimal | None


class NrvReportOut(Schema):
    as_of: date
    cost_to_sell_pct: Decimal
    writedown_enabled: bool
    stock_value: Decimal
    nrv_loss: Decimal  # what the stock is worth less than cost, in all
    holding_gain_loss: Decimal
    rows: list[NrvRowOut]


class WritedownCreate(Schema):
    location_id: int  # the shop whose number series the document uses
    item_ids: list[int] = Field(min_length=1)
    note: str | None = Field(default=None, max_length=200)


class WritedownLineOut(Schema):
    item_id: int
    item_name: str
    base_unit: str
    quantity: Decimal
    old_cost: Decimal
    new_cost: Decimal
    market_rate: Decimal
    value: Decimal


class WritedownOut(Schema):
    id: int
    number: str
    location_id: int
    writedown_date: date
    note: str | None
    total: Decimal
    lines: list[WritedownLineOut]


class FifoLayerOut(Schema):
    received: date
    quantity: Decimal
    age_days: int


class FifoItemOut(Schema):
    item_id: int
    item_name: str
    base_unit: str
    on_hand: Decimal
    oldest_age_days: int | None
    buckets: dict[str, Decimal]
    over_90_value: Decimal  # the oldest stock at average cost
    layers: list[FifoLayerOut]


class FifoAgeOut(Schema):
    as_of: date
    note: str
    items: list[FifoItemOut]


class SupplierShortageOut(Schema):
    party_id: int
    party_name: str
    lines: int
    goods_value: Decimal
    shortage_value: Decimal
    shortage_pct: Decimal | None  # of the value billed
    short_lines: int


class ShortageClaimOut(Schema):
    purchase_number: str
    bill_no: str
    bill_date: date
    party_name: str
    item_name: str
    base_unit: str
    billed_qty: Decimal
    received_qty: Decimal
    shortage_qty: Decimal
    loss_pct: Decimal
    value: Decimal


class ShrinkageOut(Schema):
    date_from: date
    date_to: date
    shortage_value: Decimal
    suppliers: list[SupplierShortageOut]
    claims: list[ShortageClaimOut]
