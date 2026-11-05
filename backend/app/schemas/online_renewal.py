"""Plan & billing for a company owner: renew Duolink online with Razorpay (Milestone 30).

These are Duolink's prices and the company's own payments to Duolink, shown only to its owner.
The browser names a price; the amount is always the server's. No secret is ever in an answer:
`key_id` is Razorpay's public key id, which Checkout needs in the browser.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.schemas.common import Schema


class RenewalOption(Schema):
    price_id: int
    plan_id: int
    plan_code: str
    plan_name: str
    plan_description: str
    duration_value: int
    duration_unit: str
    price: Decimal
    currency: str
    is_current_plan: bool
    # Paying for this option now would make the plan run until this moment.
    would_run_until: datetime


class RenewalOverview(Schema):
    online_renewal: bool  # false: "Contact Duolink to renew"
    plan_code: str
    plan_name: str
    status: Literal["trial", "active", "expired", "cancelled"]
    access_state: Literal["full", "read_only"]
    expires_at: datetime | None
    days_left: int | None
    options: list[RenewalOption]  # empty while online renewal is off


class RenewalOrderCreate(Schema):
    """Which of the plan prices to pay for. Nothing else is read: the amount comes from it."""

    price_id: int


class RenewalOrderOut(Schema):
    """What Razorpay Checkout is opened with."""

    id: int
    razorpay_order_id: str
    key_id: str
    amount: Decimal
    amount_paise: int
    currency: str
    name: str  # who is paid: Duolink
    description: str  # "Business plan, 1 year"
    company_name: str


class VerifyRequest(Schema):
    """What Razorpay Checkout hands back after a payment."""

    razorpay_order_id: str = Field(min_length=1, max_length=40)
    razorpay_payment_id: str = Field(min_length=1, max_length=40)
    razorpay_signature: str = Field(min_length=1, max_length=128)


class RenewalResult(Schema):
    applied: bool  # false: this payment had already been recorded (by the webhook, say)
    plan_name: str
    status: Literal["trial", "active", "expired", "cancelled"]
    access_state: Literal["full", "read_only"]
    expires_at: datetime | None
    days_left: int | None


class WebhookAnswer(Schema):
    status: Literal["applied", "duplicate", "ignored"]
