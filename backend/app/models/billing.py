"""What a company pays Duolink for the service (Milestone 21, ADR 0013).

Both tables belong to a company (`tenant_id`, row-level security, platform policy) but only
Duolink's admin writes them, under `/admin/billing`. A payment row is Duolink's receipt record:
Duolink's GST tax invoice for the subscription is raised in Duolink's own books.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ActorMixin, Audited, Base, IntPK, TenantMixin, TimestampMixin
from app.models.enums import (
    PaymentMethod,
    SubscriptionOrderStatus,
    SubscriptionStatus,
    str_enum,
)


class Subscription(Base, TenantMixin, TimestampMixin):
    """One per company: the plan it is on and until when. A renewal moves `expires_at`; the
    payments below are the history."""

    __tablename__ = "subscription"
    __table_args__ = (UniqueConstraint("tenant_id"),)

    id: Mapped[IntPK]
    plan_id: Mapped[int] = mapped_column(ForeignKey("platform_plan.id"), index=True)
    # The price option bought last, kept as text of the terms so a later edit of the plan's
    # prices does not rewrite history. Blank for a trial or an import.
    duration_value: Mapped[int | None] = mapped_column(Integer)
    duration_unit: Mapped[str | None] = mapped_column(String(10))
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    status: Mapped[SubscriptionStatus] = mapped_column(
        str_enum(SubscriptionStatus, "subscription_status")
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    # Set by the migration for a company that was active with no end date: Duolink should
    # confirm the date it was given.
    needs_review: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)


class SubscriptionPayment(Base, TenantMixin, TimestampMixin):
    """Append-only (the database refuses UPDATE and DELETE). A mistaken payment is cancelled out
    by a row of the opposite sign that points at it with `reverses_id`."""

    __tablename__ = "subscription_payment"
    __table_args__ = (
        # A payment is reversed at most once.
        Index(
            "uq_subscription_payment_reverses_id",
            "reverses_id",
            unique=True,
            postgresql_where=text("reverses_id IS NOT NULL"),
        ),
        # A Razorpay payment id lands once, however often Checkout and the webhook report it
        # (Milestone 30). Across all companies: a payment id is Razorpay's, and unique there.
        Index(
            "uq_subscription_payment_razorpay_reference",
            "reference",
            unique=True,
            postgresql_where=text("method = 'razorpay'"),
        ),
        # Only an online payment is recorded without a Duolink admin.
        CheckConstraint(
            "recorded_by_admin_id IS NOT NULL OR (method = 'razorpay' AND reverses_id IS NULL)",
            name="recorded_by_admin_or_online",
        ),
    )

    id: Mapped[IntPK]
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscription.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("platform_plan.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    method: Mapped[PaymentMethod] = mapped_column(str_enum(PaymentMethod, "payment_method"))
    reference: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # The paid period this payment bought; blank on a reversal.
    period_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    period_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reverses_id: Mapped[int | None] = mapped_column(ForeignKey("subscription_payment.id"))
    # Blank for a payment the company made online (Milestone 30).
    recorded_by_admin_id: Mapped[int | None] = mapped_column(ForeignKey("platform_admin.id"))


class SubscriptionOrder(Base, Audited, TenantMixin, TimestampMixin, ActorMixin):
    """An owner asked to pay online (Milestone 30): the Razorpay order made for one plan price.

    The terms bought (plan, duration, amount) are copied from the price when the order is made,
    so a later edit of the plan's prices cannot change what was paid for. The amount is the
    server's, never the browser's. Once paid, the order points at the payment row it made.
    """

    __tablename__ = "subscription_order"

    id: Mapped[IntPK]
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscription.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("platform_plan.id"))
    # The price option chosen, for reference only: a plan's prices can be replaced later.
    price_id: Mapped[int | None] = mapped_column(Integer)
    duration_value: Mapped[int] = mapped_column(Integer)
    duration_unit: Mapped[str] = mapped_column(String(10))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    razorpay_order_id: Mapped[str] = mapped_column(String(40), unique=True)
    receipt: Mapped[str] = mapped_column(String(40))
    status: Mapped[SubscriptionOrderStatus] = mapped_column(
        str_enum(SubscriptionOrderStatus, "subscription_order_status")
    )
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(40))
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("subscription_payment.id"))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Which report landed it first: "checkout" (the browser) or "webhook" (Razorpay).
    paid_via: Mapped[str | None] = mapped_column(String(10))
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"))


__all__ = ["Subscription", "SubscriptionOrder", "SubscriptionPayment"]
