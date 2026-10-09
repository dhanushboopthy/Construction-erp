"""Item master and parties (Milestone 2): items with unit conversions, customers, suppliers
and the delivery sites of each customer."""

from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    ActorMixin,
    Audited,
    Base,
    IntPK,
    Money,
    Percent,
    TenantMixin,
    TimestampMixin,
    UnitCost,
)
from app.models.enums import CustomerSegment, ItemCategory, PartyType, str_enum


class Item(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    __tablename__ = "item"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name"),
        CheckConstraint("hsn ~ '^[0-9]{4,8}$'", name="hsn_format"),
    )

    id: Mapped[IntPK]
    name: Mapped[str] = mapped_column(String(150))
    category: Mapped[ItemCategory] = mapped_column(str_enum(ItemCategory, "item_category"))
    brand: Mapped[str | None] = mapped_column(String(80))  # G8
    hsn: Mapped[str] = mapped_column(String(8))  # stored with 8 digits where known (G16)
    gst_rate: Mapped[Percent] = mapped_column()
    base_unit: Mapped[str] = mapped_column(String(16))
    base_whole_only: Mapped[bool] = mapped_column(Boolean, default=False)  # bags, pieces
    size: Mapped[str | None] = mapped_column(String(50))
    grade: Mapped[str | None] = mapped_column(String(50))
    weight_per_piece_kg: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))  # G7
    # Owner only: the least margin per base unit before the owner is warned (B5).
    min_margin: Mapped[UnitCost] = mapped_column(default=Decimal("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    units: Mapped[list["ItemUnit"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="ItemUnit.unit"
    )

    __audit_exclude__ = frozenset({"updated_at"})


class ItemUnit(Base, TenantMixin):
    """Other units an item is bought or sold in, with the factor to its base unit."""

    __tablename__ = "item_unit"
    __table_args__ = (UniqueConstraint("item_id", "unit"),)

    id: Mapped[IntPK]
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id", ondelete="CASCADE"))
    unit: Mapped[str] = mapped_column(String(16))
    factor_to_base: Mapped[Decimal] = mapped_column(Numeric(14, 6))
    whole_only: Mapped[bool] = mapped_column(Boolean, default=False)


class Party(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    __tablename__ = "party"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)

    id: Mapped[IntPK]
    name: Mapped[str] = mapped_column(String(150))
    type: Mapped[PartyType] = mapped_column(str_enum(PartyType, "party_type"))
    segment: Mapped[CustomerSegment | None] = mapped_column(
        str_enum(CustomerSegment, "customer_segment")
    )
    gstin: Mapped[str | None] = mapped_column(String(15))
    state_code: Mapped[str] = mapped_column(String(2))
    address: Mapped[str] = mapped_column(Text, default="")
    phone: Mapped[str | None] = mapped_column(String(20))
    credit_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    # Null means "use the shop default" from shop_settings (B8).
    credit_limit: Mapped[Money | None] = mapped_column()
    credit_days: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    sites: Mapped[list["Site"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="Site.name"
    )

    __audit_exclude__ = frozenset({"updated_at"})


class Site(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    """A customer's delivery site; each invoice belongs to one site (B9, G22)."""

    __tablename__ = "site"
    __table_args__ = (UniqueConstraint("party_id", "name"),)

    id: Mapped[IntPK]
    party_id: Mapped[int] = mapped_column(ForeignKey("party.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(150))
    address: Mapped[str] = mapped_column(Text, default="")
    state_code: Mapped[str] = mapped_column(String(2))
    gstin: Mapped[str | None] = mapped_column(String(15))  # null prints as "URP" (G13)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __audit_exclude__ = frozenset({"updated_at"})
