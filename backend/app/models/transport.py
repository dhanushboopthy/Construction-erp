"""Hired vehicles, trips and freight (B18), and the link from a direct sale line to the supplier
purchase that supplies it (B10). Milestone 9."""

from datetime import date

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    ActorMixin,
    Audited,
    Base,
    IntPK,
    Money,
    Quantity,
    TenantMixin,
    TimestampMixin,
    UnitCost,
)


class Vehicle(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    """A lorry or tempo. Hired ones are paid through `party_id` (a supplier account); our own
    vehicles (`is_own`, for the future) carry no payable."""

    __tablename__ = "vehicle"
    __table_args__ = (UniqueConstraint("tenant_id", "number"),)

    id: Mapped[IntPK]
    number: Mapped[str] = mapped_column(String(20))
    owner_name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(20))
    is_own: Mapped[bool] = mapped_column(Boolean, default=False)
    party_id: Mapped[int | None] = mapped_column(ForeignKey("party.id", ondelete="RESTRICT"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __audit_exclude__ = frozenset({"updated_at"})


class Trip(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    """One run of one vehicle. Freight is payable to the vehicle's owner; a trip tied to a sale
    reduces that sale's profit, one tied to a purchase is part of that purchase's cost already
    (as a charge), so it is only recorded here for the payable."""

    __tablename__ = "trip"
    __table_args__ = (
        CheckConstraint("freight_amount >= 0", name="freight_not_negative"),
        Index("ix_trip_invoice", "invoice_id"),
        Index("ix_trip_date", "trip_date"),
    )

    id: Mapped[IntPK]
    trip_date: Mapped[date] = mapped_column(Date)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicle.id", ondelete="RESTRICT"))
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id", ondelete="RESTRICT"))
    invoice_id: Mapped[int | None] = mapped_column(
        ForeignKey("sales_invoice.id", ondelete="RESTRICT")
    )
    purchase_id: Mapped[int | None] = mapped_column(ForeignKey("purchase.id", ondelete="RESTRICT"))
    from_place: Mapped[str] = mapped_column(String(150))
    to_place: Mapped[str] = mapped_column(String(150))
    freight_amount: Mapped[Money] = mapped_column()
    note: Mapped[str | None] = mapped_column(String(300))

    __audit_exclude__ = frozenset({"updated_at"})


class DropShipLink(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    """A direct sale line and the supplier purchase line whose goods go to the site. The landed
    cost is copied here so the sale's profit stays fixed (the sale line itself is never edited)."""

    __tablename__ = "drop_ship_link"
    __table_args__ = (
        UniqueConstraint("sales_line_id"),
        CheckConstraint("base_qty > 0", name="positive_qty"),
        Index("ix_drop_ship_link_purchase_line", "purchase_line_id"),
    )

    id: Mapped[IntPK]
    sales_line_id: Mapped[int] = mapped_column(ForeignKey("sales_line.id", ondelete="RESTRICT"))
    purchase_line_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_line.id", ondelete="RESTRICT")
    )
    base_qty: Mapped[Quantity] = mapped_column()
    unit_cost: Mapped[UnitCost] = mapped_column()

    __audit_exclude__ = frozenset({"updated_at"})
