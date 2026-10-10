from datetime import date
from decimal import Decimal
from typing import Annotated, Self

from pydantic import Field, model_validator

from app.domain.inventory_analytics import AdjustmentReason, Direction
from app.models.enums import CountStatus
from app.schemas.common import Schema

Qty = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]


class TransferLineIn(Schema):
    item_id: int
    quantity: Qty
    unit: str | None = Field(default=None, max_length=16)  # blank means the item's base unit


class TransferCreate(Schema):
    from_location_id: int
    to_location_id: int
    transfer_date: date | None = None
    note: str | None = Field(default=None, max_length=200)
    lines: list[TransferLineIn] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _different(self) -> Self:
        if self.from_location_id == self.to_location_id:
            raise ValueError("Choose two different places")
        return self


class TransferLineOut(Schema):
    item_id: int
    item_name: str
    base_unit: str
    quantity: Decimal


class TransferOut(Schema):
    id: int
    number: str
    from_location_id: int
    from_code: str
    to_location_id: int
    to_code: str
    transfer_date: date
    note: str | None
    lines: list[TransferLineOut]


class CountCreate(Schema):
    location_id: int
    count_date: date | None = None
    item_ids: list[int] | None = None  # blank: every item with stock here
    note: str | None = Field(default=None, max_length=200)


class CountLineIn(Schema):
    item_id: int
    counted_qty: Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=3)] | None


class CountLinesUpdate(Schema):
    lines: list[CountLineIn] = Field(min_length=1)


class CountLineOut(Schema):
    item_id: int
    item_name: str
    base_unit: str
    system_qty: Decimal
    counted_qty: Decimal | None
    variance: Decimal | None


class CountLineOwnerOut(CountLineOut):
    variance_value: Decimal | None


class CountOut(Schema):
    id: int
    location_id: int
    location_code: str
    count_date: date
    status: CountStatus
    note: str | None
    lines: list[CountLineOut]


class CountOwnerOut(CountOut):
    lines: list[CountLineOwnerOut]  # type: ignore[assignment]
    total_variance_value: Decimal


# ---------------------------------------------------------------------------- adjustments (FM2)


class AdjustmentLineIn(Schema):
    item_id: int
    quantity: Qty
    unit: str | None = Field(default=None, max_length=16)  # blank means the item's base unit
    direction: Direction | None = None  # blank: the only direction the reason allows


class AdjustmentCreate(Schema):
    location_id: int
    adjustment_date: date | None = None
    reason: AdjustmentReason
    note: str | None = Field(default=None, max_length=200)
    lines: list[AdjustmentLineIn] = Field(min_length=1, max_length=100)
    approval_ids: list[int] = Field(default_factory=list, max_length=5)


class AdjustmentLineOut(Schema):
    item_id: int
    item_name: str
    base_unit: str
    direction: Direction
    quantity: Decimal


class AdjustmentLineOwnerOut(AdjustmentLineOut):
    unit_cost: Decimal
    value: Decimal  # lost (+) or gained (-)


class AdjustmentOut(Schema):
    id: int
    number: str
    location_id: int
    location_code: str
    adjustment_date: date
    reason: AdjustmentReason
    reason_label: str
    note: str | None
    approved: bool
    created_by_name: str | None
    lines: list[AdjustmentLineOut]


class AdjustmentOwnerOut(AdjustmentOut):
    lines: list[AdjustmentLineOwnerOut]  # type: ignore[assignment]
    value: Decimal  # net value lost (+) or gained (-)
    itc_to_reverse: Decimal


class ReasonTotal(Schema):
    reason: AdjustmentReason
    reason_label: str
    value: Decimal  # lost (+) or gained (-)


class AdjustmentBookOut(Schema):
    date_from: date
    date_to: date
    location_id: int | None
    entries: list[AdjustmentOut]


class AdjustmentBookOwnerOut(AdjustmentBookOut):
    entries: list[AdjustmentOwnerOut]  # type: ignore[assignment]
    by_reason: list[ReasonTotal]
    net_loss: Decimal
    itc_to_reverse: Decimal


class ItcReversalRow(Schema):
    entry_date: date
    document: str  # adjustment number, or "Count 12" for a posted count
    location_code: str
    item_name: str
    hsn: str
    reason: AdjustmentReason
    reason_label: str
    quantity: Decimal
    base_unit: str
    value: Decimal  # cost of the goods lost, excl. GST
    gst_rate: Decimal
    itc: Decimal


class ItcReversalOut(Schema):
    period: str
    date_from: date
    date_to: date
    includes_shortages: bool  # the itc_reverse_shortages setting
    rows: list[ItcReversalRow]
    total_value: Decimal
    total_itc: Decimal
    note: str
