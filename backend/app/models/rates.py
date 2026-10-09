"""Selling rates (Milestone 5, rule B3): the daily market rate, customer-specific rates, and
the owner's target margin per item. Rates are stored per base unit, excluding GST (G2)."""

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ActorMixin, Audited, Base, IntPK, TenantMixin, TimestampMixin

Rate = Numeric(14, 6)


class MarketRate(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    """One selling rate per item per day. The latest on or before a bill date applies."""

    __tablename__ = "market_rate"
    __table_args__ = (
        UniqueConstraint("tenant_id", "item_id", "effective_date"),
        CheckConstraint("rate >= 0", name="non_negative"),
        Index("ix_market_rate_lookup", "item_id", "effective_date"),
    )

    id: Mapped[IntPK]
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id", ondelete="RESTRICT"))
    effective_date: Mapped[date] = mapped_column(Date)
    rate: Mapped[Decimal] = mapped_column(Rate)  # per base unit, excluding GST
    entered_unit: Mapped[str] = mapped_column(String(16))  # what the owner typed it in
    entered_rate: Mapped[Decimal] = mapped_column(Numeric(14, 4))  # as typed, per entered unit

    __audit_exclude__ = frozenset({"updated_at"})


class CustomerRate(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    """A rate agreed with one customer for one item, for a period. Beats the market rate."""

    __tablename__ = "customer_rate"
    __table_args__ = (
        CheckConstraint("rate >= 0", name="non_negative"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="period_order"),
        Index("ix_customer_rate_lookup", "party_id", "item_id", "valid_from"),
    )

    id: Mapped[IntPK]
    party_id: Mapped[int] = mapped_column(ForeignKey("party.id", ondelete="RESTRICT"))
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id", ondelete="RESTRICT"))
    rate: Mapped[Decimal] = mapped_column(Rate)
    entered_unit: Mapped[str] = mapped_column(String(16))
    entered_rate: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __audit_exclude__ = frozenset({"updated_at"})


class ItemMargin(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    """The owner's target margin per base unit, used to suggest a selling rate. Owner only."""

    __tablename__ = "item_margin"
    __table_args__ = (
        UniqueConstraint("tenant_id", "item_id"),
        CheckConstraint("margin_per_base_unit >= 0", name="non_negative"),
    )

    id: Mapped[IntPK]
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id", ondelete="CASCADE"))
    margin_per_base_unit: Mapped[Decimal] = mapped_column(Numeric(14, 6))

    __audit_exclude__ = frozenset({"updated_at"})
