"""Supplier target schemes (B15, Milestone 11). Progress is never stored: it is worked out from
purchases and returns in the period, so it cannot disagree with them. Only the earned rebate
is recorded, once, when the owner books it."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.schemes import RebateRule
from app.models.base import (
    ActorMixin,
    Audited,
    Base,
    IntPK,
    Money,
    Quantity,
    TenantMixin,
    TimestampMixin,
)
from app.models.enums import ItemCategory, str_enum


class SupplierScheme(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    __tablename__ = "supplier_scheme"
    __table_args__ = (
        CheckConstraint("target_qty > 0", name="positive_target"),
        CheckConstraint("period_end >= period_start", name="period_order"),
        CheckConstraint("(item_id IS NULL) <> (category IS NULL)", name="item_or_category"),
        Index("ix_supplier_scheme_party", "party_id"),
    )

    id: Mapped[IntPK]
    party_id: Mapped[int] = mapped_column(ForeignKey("party.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(100))
    item_id: Mapped[int | None] = mapped_column(ForeignKey("item.id", ondelete="RESTRICT"))
    category: Mapped[ItemCategory | None] = mapped_column(str_enum(ItemCategory, "item_category"))
    unit: Mapped[str] = mapped_column(String(16))  # base unit the target is counted in
    target_qty: Mapped[Quantity] = mapped_column()
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    rebate_rule: Mapped[RebateRule] = mapped_column(str_enum(RebateRule, "rebate_rule"))
    rebate_value: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    rebate_amount: Mapped[Money | None] = mapped_column()
    rebate_booked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __audit_exclude__ = frozenset({"updated_at"})
