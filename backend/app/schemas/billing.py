"""Duolink's own pricing: plans and their prices (Milestone 20, ADR 0013).

This is Duolink's revenue, not a company's money. It is the only admin shape allowed to carry a
price, and only under /api/v1/admin/billing/ (test_platform_admin keeps that list explicit).
Prices are Decimal in and out; a JSON number with a fraction is refused so no float is read.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field, field_validator

from app.models.enums import DurationUnit, PaymentMethod
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


# ---------------------------------------------------------------- subscriptions (Milestone 21)


class SubscriptionRow(Schema):
    id: int
    tenant_id: int
    tenant_slug: str
    tenant_name: str
    plan_id: int
    plan_code: str
    plan_name: str
    status: Literal["trial", "active", "expired", "cancelled"]  # worked out from the dates
    starts_at: datetime
    expires_at: datetime | None
    days_left: int | None  # negative once it has ended
    needs_review: bool
    duration_value: int | None
    duration_unit: str | None
    price: Decimal | None
    cancelled_at: datetime | None
    cancel_reason: str | None


class RenewRequest(Schema):
    """Record a renewal Duolink received by hand. Choose one of the plan's price options
    (`price_id`) or `custom_days`. `amount` is what was actually received, as text."""

    plan_id: int
    price_id: int | None = None
    custom_days: int | None = Field(default=None, ge=1, le=3650)
    amount: Decimal = Field(max_digits=12, decimal_places=2)
    method: PaymentMethod
    reference: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=1000)
    paid_at: datetime | None = None

    @field_validator("amount", mode="before")
    @classmethod
    def _text_not_float(cls, value: Any) -> Any:
        return _no_float(value)


class CancelRequest(Schema):
    reason: str = Field(min_length=3, max_length=500)


class ReverseRequest(Schema):
    reason: str = Field(min_length=3, max_length=500)


class PaymentOut(Schema):
    id: int
    subscription_id: int
    tenant_id: int
    tenant_name: str
    plan_code: str
    plan_name: str
    amount: Decimal  # negative on a reversal
    method: PaymentMethod
    reference: str | None
    notes: str | None
    paid_at: datetime
    period_starts_at: datetime | None
    period_ends_at: datetime | None
    reverses_id: int | None
    reversed: bool
    recorded_by: str


class PaymentTotals(Schema):
    received: Decimal
    reversed: Decimal  # as a positive amount
    net: Decimal


class PaymentPage(Schema):
    items: list[PaymentOut]
    total: int
    limit: int
    offset: int
    totals: PaymentTotals  # for the whole filter, not just this page


class CompaniesByStatus(Schema):
    trial: int
    active: int
    suspended: int
    cancelled: int


class TrendPoint(Schema):
    month: str  # 2026-11
    revenue: Decimal
    signups: int


class PlanShare(Schema):
    plan_id: int
    plan_code: str
    plan_name: str
    companies: int


class ExpiringSoon(Schema):
    tenant_id: int
    tenant_name: str
    plan_code: str
    expires_at: datetime
    days_left: int


class BillingDashboard(Schema):
    companies_by_status: CompaniesByStatus
    active_subscriptions: int
    revenue_month: Decimal
    revenue_fy: Decimal
    new_companies_month: int
    renewals_month: int
    expiring_30: int
    trend: list[TrendPoint]
    plan_breakdown: list[PlanShare]
    expiring_soon: list[ExpiringSoon]
