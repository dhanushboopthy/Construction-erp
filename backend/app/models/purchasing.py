"""Purchases with landed cost, the charge master, and payments (Milestone 4)."""

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.landed_cost import ChargeBasis
from app.models.base import (
    ActorMixin,
    Audited,
    Base,
    IntPK,
    Money,
    Percent,
    Quantity,
    TenantMixin,
    TimestampMixin,
    UnitCost,
)
from app.models.enums import PaymentDirection, PaymentMode, PurchaseMode, PurchaseStatus, str_enum


class CostComponent(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    """A kind of charge added to a purchase line (unloading, weighbridge, transport...).
    The default amount is only a suggestion; each purchase line stores its own amount."""

    __tablename__ = "cost_component"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)

    id: Mapped[IntPK]
    name: Mapped[str] = mapped_column(String(60))
    basis: Mapped[ChargeBasis] = mapped_column(str_enum(ChargeBasis, "charge_basis"))
    default_amount: Mapped[Money] = mapped_column(default=Decimal("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __audit_exclude__ = frozenset({"updated_at"})


class Purchase(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    """A posted supplier bill. Never edited: corrections are purchase returns and debit notes."""

    __tablename__ = "purchase"
    __table_args__ = (
        UniqueConstraint("tenant_id", "number"),
        # The same supplier bill cannot be entered twice.
        UniqueConstraint("tenant_id", "supplier_id", "bill_no"),
        Index("ix_purchase_date", "bill_date"),
    )

    id: Mapped[IntPK]
    number: Mapped[str] = mapped_column(String(16))
    supplier_id: Mapped[int] = mapped_column(ForeignKey("party.id", ondelete="RESTRICT"))
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id", ondelete="RESTRICT"))
    bill_no: Mapped[str] = mapped_column(String(40))
    bill_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    mode: Mapped[PurchaseMode] = mapped_column(str_enum(PurchaseMode, "purchase_mode"))
    status: Mapped[PurchaseStatus] = mapped_column(
        str_enum(PurchaseStatus, "purchase_status"), default=PurchaseStatus.POSTED
    )
    goods_value: Mapped[Money] = mapped_column()
    gst_amount: Mapped[Money] = mapped_column()
    charges_total: Mapped[Money] = mapped_column()
    supplier_payable: Mapped[Money] = mapped_column()
    note: Mapped[str | None] = mapped_column(Text)

    lines: Mapped[list["PurchaseLine"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="PurchaseLine.line_no"
    )

    __audit_exclude__ = frozenset({"updated_at"})


class PurchaseLine(Base, TenantMixin):
    __tablename__ = "purchase_line"
    __table_args__ = (
        UniqueConstraint("purchase_id", "line_no"),
        CheckConstraint("billed_qty > 0 AND received_qty > 0", name="positive_qty"),
    )

    id: Mapped[IntPK]
    purchase_id: Mapped[int] = mapped_column(ForeignKey("purchase.id", ondelete="CASCADE"))
    line_no: Mapped[int] = mapped_column(Integer)
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id", ondelete="RESTRICT"))
    unit: Mapped[str] = mapped_column(String(16))  # the unit the bill was written in
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))  # billed, in `unit`
    received_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))  # received, in `unit`
    billed_qty: Mapped[Quantity] = mapped_column()  # base units
    received_qty: Mapped[Quantity] = mapped_column()  # base units
    rate: Mapped[Decimal] = mapped_column(Numeric(14, 4))  # per `unit`, excluding GST
    gst_rate: Mapped[Percent] = mapped_column()
    goods_value: Mapped[Money] = mapped_column()
    gst_amount: Mapped[Money] = mapped_column()
    charges_total: Mapped[Money] = mapped_column()
    total_cost: Mapped[Money] = mapped_column()
    unit_cost: Mapped[UnitCost] = mapped_column()  # landed cost per base unit (owner only)

    costs: Mapped[list["PurchaseCost"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="PurchaseCost.id"
    )


class PurchaseCost(Base, TenantMixin):
    """One charge on one purchase line (rule B2)."""

    __tablename__ = "purchase_cost"

    id: Mapped[IntPK]
    purchase_line_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_line.id", ondelete="CASCADE")
    )
    component_id: Mapped[int | None] = mapped_column(
        ForeignKey("cost_component.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(60))
    basis: Mapped[ChargeBasis] = mapped_column(str_enum(ChargeBasis, "charge_basis"))
    rate: Mapped[Money] = mapped_column()  # per ton, per base unit, per trip or flat
    total: Mapped[Money] = mapped_column()
    on_supplier_bill: Mapped[bool] = mapped_column(Boolean, default=False)


class Payment(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    """Money received from a customer or paid to a supplier. Created in Milestone 4 for supplier
    advances and payments; Milestone 7 adds customer receipts, credit checks and cash limits."""

    __tablename__ = "payment"
    __table_args__ = (
        UniqueConstraint("tenant_id", "number"),
        UniqueConstraint("tenant_id", "idempotency_key"),
        CheckConstraint("amount > 0", name="positive_amount"),
    )

    id: Mapped[IntPK]
    number: Mapped[str] = mapped_column(String(16))
    direction: Mapped[PaymentDirection] = mapped_column(
        str_enum(PaymentDirection, "payment_direction")
    )
    party_id: Mapped[int] = mapped_column(ForeignKey("party.id", ondelete="RESTRICT"))
    site_id: Mapped[int | None] = mapped_column(ForeignKey("site.id", ondelete="RESTRICT"))
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id", ondelete="RESTRICT"))
    amount: Mapped[Money] = mapped_column()
    mode: Mapped[PaymentMode] = mapped_column(str_enum(PaymentMode, "payment_mode"))
    reference: Mapped[str | None] = mapped_column(String(60))
    payment_date: Mapped[date] = mapped_column(Date)
    idempotency_key: Mapped[str | None] = mapped_column(String(80))
    note: Mapped[str | None] = mapped_column(String(200))

    __audit_exclude__ = frozenset({"updated_at"})
