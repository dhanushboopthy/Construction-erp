"""Duolink's own pricing: plans and their prices (Milestone 20, ADR 0013).

This is Duolink's revenue, not a company's money. It is the only admin shape allowed to carry a
price, and only under /api/v1/admin/billing/ (test_platform_admin keeps that list explicit).
Prices are Decimal in and out; a JSON number with a fraction is refused so no float is read.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import Field, field_validator

from app.models.enums import DurationUnit
from app.schemas.common import Schema


def _no_float(value: Any) -> Any:
    if isinstance(value, float):
        raise ValueError('Send the price as text, such as "999.90"')
    return value


class PlanPriceIn(Schema):
    duration_value: int = Field(ge=1, le=3650)
    duration_unit: DurationUnit
    price: Decimal = Field(max_digits=12, decimal_places=2)
    is_active: bool = True

    @field_validator("price", mode="before")
    @classmethod
    def _text_not_float(cls, value: Any) -> Any:
        return _no_float(value)


class PlanPriceOut(Schema):
    id: int
    duration_value: int
    duration_unit: DurationUnit
    price: Decimal
    currency: str
    is_active: bool


class PlanCreate(Schema):
    """`code` is upper snake case; spaces and hyphens become underscores. A plan has 1 to 6
    prices, each with its own duration."""

    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=100)
    short_description: str = Field(default="", max_length=200)
    long_description: str = Field(default="", max_length=4000)
    max_users: int = Field(ge=1, le=100000)
    max_locations: int = Field(ge=1, le=10000)
    features: list[str] = Field(default_factory=list, max_length=20)
    is_popular: bool = False
    sort_order: int = Field(default=0, ge=0, le=10000)
    prices: list[PlanPriceIn] = Field(max_length=20)
    reason: str | None = Field(default=None, max_length=500)


class PlanUpdate(Schema):
    """Send only what changes. `prices`, when sent, replaces the whole list. Setting
    `is_popular` clears it on the plan that had it; an archived plan cannot be popular."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    short_description: str | None = Field(default=None, max_length=200)
    long_description: str | None = Field(default=None, max_length=4000)
    max_users: int | None = Field(default=None, ge=1, le=100000)
    max_locations: int | None = Field(default=None, ge=1, le=10000)
    features: list[str] | None = Field(default=None, max_length=20)
    is_active: bool | None = None
    is_popular: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=10000)
    prices: list[PlanPriceIn] | None = Field(default=None, max_length=20)
    reason: str | None = Field(default=None, max_length=500)


class PlanReason(Schema):
    reason: str = Field(min_length=3, max_length=500)


class PlanDelete(Schema):
    """`confirmation` must be the word DELETE, typed exactly."""

    confirmation: str = Field(max_length=20)
    reason: str = Field(min_length=3, max_length=500)


class PlanOut(Schema):
    id: int
    code: str
    name: str
    short_description: str
    long_description: str
    max_users: int
    max_locations: int
    features: list[str]
    is_active: bool
    is_popular: bool
    sort_order: int
    prices: list[PlanPriceOut]
    companies: int  # how many companies are on this plan
    created_at: datetime
    updated_at: datetime


class PlanFeatureOut(Schema):
    code: str
    name: str
    description: str
