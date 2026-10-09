from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import Field, ValidationInfo, field_validator

from app.domain.pricing import RateSource
from app.schemas.common import Schema

Money4 = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=4)]


class RateEntry(Schema):
    item_id: int
    rate: Money4
    unit: str | None = Field(default=None, max_length=16)  # blank: the item's base unit


class MarketRatesPut(Schema):
    effective_date: date
    rates: list[RateEntry] = Field(min_length=1, max_length=500)


class RateRowOut(Schema):
    """Selling rate for one item as of a date. Staff see this; no cost, no margin (rule B4)."""

    item_id: int
    item_name: str
    base_unit: str
    rate: Decimal | None  # per base unit, excluding GST
    effective_date: date | None
    previous_rate: Decimal | None
    units: list[str]
    # The same figures in the unit the owner quotes in (per ton for steel), converted here so the
    # screen does no money maths of its own.
    quote_unit: str
    rate_quoted: Decimal | None
    previous_quoted: Decimal | None


class RateRowOwnerOut(RateRowOut):
    avg_cost: Decimal | None
    margin_per_unit: Decimal | None
    suggested_rate: Decimal | None
    margin_now: Decimal | None  # selling rate less average cost
    avg_cost_quoted: Decimal | None
    margin_quoted: Decimal | None
    suggested_quoted: Decimal | None
    margin_now_quoted: Decimal | None
    below_cost: bool
    below_min_margin: bool


class RateWarning(Schema):
    item_id: int
    item_name: str
    below_cost: bool
    below_min_margin: bool


class MarketRatesResult(Schema):
    saved: int
    warnings: list[RateWarning]


class HistoryPoint(Schema):
    effective_date: date
    rate: Decimal
    entered_unit: str
    entered_rate: Decimal


class CustomerRateCreate(Schema):
    party_id: int
    item_id: int
    rate: Money4
    unit: str | None = Field(default=None, max_length=16)
    valid_from: date
    valid_to: date | None = None

    @field_validator("valid_to")
    @classmethod
    def _ordered(cls, value: date | None, info: ValidationInfo) -> date | None:
        start = info.data.get("valid_from")
        if value and start and value < start:
            raise ValueError("The end date cannot be before the start date")
        return value


class CustomerRateUpdate(Schema):
    valid_to: date | None = None
    is_active: bool | None = None


class CustomerRateOut(Schema):
    id: int
    party_id: int
    party_name: str
    item_id: int
    item_name: str
    rate: Decimal
    entered_unit: str
    entered_rate: Decimal
    valid_from: date
    valid_to: date | None
    is_active: bool


class MarginPut(Schema):
    item_id: int
    margin: Money4
    unit: str | None = Field(default=None, max_length=16)


class MarginOut(Schema):
    item_id: int
    item_name: str
    base_unit: str
    margin_per_unit: Decimal
    min_margin: Decimal


class ResolvedPriceOut(Schema):
    item_id: int
    party_id: int | None
    on: date
    rate: Decimal  # per base unit, excluding GST
    base_unit: str
    source: RateSource
