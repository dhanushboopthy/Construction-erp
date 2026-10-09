from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Self

from pydantic import Field, model_validator

from app.domain.schemes import RebateRule
from app.models.enums import ItemCategory
from app.schemas.common import Schema

Target = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]
RebateValue = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=4)]


class SchemeCreate(Schema):
    party_id: int
    name: str = Field(min_length=2, max_length=100)
    item_id: int | None = None
    category: ItemCategory | None = None
    unit: str | None = Field(default=None, max_length=16)  # base unit; needed for a category
    target_qty: Target
    period_start: date
    period_end: date
    rebate_rule: RebateRule
    rebate_value: RebateValue

    @model_validator(mode="after")
    def _shape(self) -> Self:
        if (self.item_id is None) == (self.category is None):
            raise ValueError("Choose one item or one category")
        if self.category is not None and not self.unit:
            raise ValueError("Say which unit the target is counted in (kg, bag...)")
        if self.period_end < self.period_start:
            raise ValueError("The period cannot end before it starts")
        if self.rebate_rule is RebateRule.PERCENT and self.rebate_value > 100:
            raise ValueError("A percentage rebate cannot be more than 100")
        return self


class SchemeUpdate(Schema):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    is_active: bool | None = None


class SchemeOut(Schema):
    id: int
    party_id: int
    party_name: str
    name: str
    item_id: int | None
    item_name: str | None
    category: ItemCategory | None
    unit: str
    target_qty: Decimal
    period_start: date
    period_end: date
    rebate_rule: RebateRule
    rebate_value: Decimal
    is_active: bool
    achieved: Decimal
    pct: Decimal
    remaining: Decimal
    reached: bool
    alert: bool
    projected_rebate: Decimal  # what it would be if booked now
    rebate_amount: Decimal | None
    rebate_booked_at: datetime | None
