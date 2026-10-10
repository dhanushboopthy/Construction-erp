"""Purchase orders, goods received, the match report, cement lots on sales and the lost-sales
log (FM10)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import Field

from app.schemas.common import Schema

Qty = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]
Rate = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=4)]

# ---------------------------------------------------------------------------- orders


class OrderLineIn(Schema):
    item_id: int
    unit: str = Field(min_length=1, max_length=16)
    quantity: Qty
    rate: Rate


class OrderCreate(Schema):
    supplier_id: int
    location_id: int
    order_date: date | None = None
    expected_date: date | None = None
    note: str | None = Field(default=None, max_length=200)
    lines: list[OrderLineIn] = Field(min_length=1, max_length=100)


class OrderLineOut(Schema):
    """Quantities only: what counter staff and the accountant see (no rate, rule B4)."""

    id: int
    line_no: int
    item_id: int
    item_name: str
    unit: str
    quantity: Decimal
    base_qty: Decimal
    base_unit: str
    received_qty: Decimal  # base units, on all receipts
    billed_qty: Decimal  # base units, on all bills


class OrderLineOwnerOut(OrderLineOut):
    rate: Decimal  # per `unit`, excluding GST
    value: Decimal


class ReceiptLineOut(Schema):
    order_line_id: int
    item_name: str
    unit: str
    quantity: Decimal
    base_qty: Decimal


class ReceiptOut(Schema):
    id: int
    number: str
    receipt_date: date
    note: str | None
    lines: list[ReceiptLineOut]


class BillRef(Schema):
    id: int
    number: str
    bill_no: str
    bill_date: date


class OrderOut(Schema):
    id: int
    number: str
    supplier_id: int
    supplier_name: str
    location_id: int
    location_code: str
    order_date: date
    expected_date: date | None
    note: str | None
    status: str  # open | received | billed
    lines: list[OrderLineOut]
    receipts: list[ReceiptOut]
    bills: list[BillRef]


class OrderOwnerOut(OrderOut):
    lines: list[OrderLineOwnerOut]  # type: ignore[assignment]
    value: Decimal


class ReceiptLineIn(Schema):
    order_line_id: int
    quantity: Qty  # in the order line's unit


class ReceiptCreate(Schema):
    receipt_date: date | None = None
    note: str | None = Field(default=None, max_length=200)
    lines: list[ReceiptLineIn] = Field(min_length=1, max_length=100)


# ---------------------------------------------------------------------------- match report


class OrderMatchRow(Schema):
    purchase_id: int
    purchase_number: str
    bill_no: str
    bill_date: date
    order_number: str
    supplier_name: str
    item_name: str
    base_unit: str
    ordered_qty: Decimal
    received_qty: Decimal
    billed_qty: Decimal  # on all bills of the order up to this one
    qty_over_received_pct: Decimal | None
    order_rate: Decimal | None  # per base unit
    bill_rate: Decimal  # per base unit
    rate_variance_pct: Decimal | None
    ppv: Decimal  # plus is money paid above the order rate
    ok: bool
    reasons: list[str]
    approved: bool  # an owner approval let it through
    entered_by_owner: bool


class MatchReport(Schema):
    date_from: date
    date_to: date
    qty_tolerance_pct: Decimal
    rate_tolerance_pct: Decimal
    rows: list[OrderMatchRow]
    bills_checked: int
    lines_checked: int
    exceptions: int
    ppv_total: Decimal


# ---------------------------------------------------------------------------- lots


class LotOut(Schema):
    label: str
    mfg_week: int | None
    mfg_year: int | None
    quantity: Decimal  # base units


# ---------------------------------------------------------------------------- lost sales


class LostSaleCreate(Schema):
    location_id: int
    item_id: int
    quantity: Qty
    unit: str | None = Field(default=None, max_length=16)  # blank: the item's base unit
    note: str | None = Field(default=None, max_length=200)
    entry_date: date | None = None  # the owner may back-date; staff are dated today


class LostSaleOut(Schema):
    """Quantities only: what counter staff see."""

    id: int
    location_id: int
    location_code: str
    entry_date: date
    item_id: int
    item_name: str
    unit: str
    quantity: Decimal
    base_qty: Decimal
    base_unit: str
    note: str | None
    entered_by: str | None
    entered_at: datetime


class LostSaleOwnerOut(LostSaleOut):
    value: Decimal | None  # base quantity x market rate on the day; None without a rate


class FillRateRow(Schema):
    item_id: int
    item_name: str
    base_unit: str
    supplied_qty: Decimal
    lost_qty: Decimal
    requested_qty: Decimal
    fill_rate_pct: Decimal | None
    lost_value: Decimal | None = None  # owner only


class FillRateReport(Schema):
    period: str
    date_from: date
    date_to: date
    location_id: int | None
    rows: list[FillRateRow]
    lines_supplied: int
    lines_lost: int
    line_fill_rate_pct: Decimal | None  # bill lines ÷ (bill lines + lost-sales entries)
    lost_value: Decimal | None = None  # owner only
