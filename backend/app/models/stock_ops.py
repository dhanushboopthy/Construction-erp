"""Stock transfers between locations and physical stock counts (Milestone 4)."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.inventory_analytics import AdjustmentReason, Direction
from app.models.base import (
    ActorMixin,
    Audited,
    Base,
    IntPK,
    Quantity,
    TenantMixin,
    TimestampMixin,
    UnitCost,
)
from app.models.enums import CountStatus, str_enum


class StockTransfer(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    """Goods moved between two of our locations. Value never changes (G6)."""

    __tablename__ = "stock_transfer"
    __table_args__ = (
        UniqueConstraint("tenant_id", "number"),
        CheckConstraint("from_location_id <> to_location_id", name="different_places"),
    )

    id: Mapped[IntPK]
    number: Mapped[str] = mapped_column(String(16))
    from_location_id: Mapped[int] = mapped_column(ForeignKey("location.id", ondelete="RESTRICT"))
    to_location_id: Mapped[int] = mapped_column(ForeignKey("location.id", ondelete="RESTRICT"))
    transfer_date: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(200))

    lines: Mapped[list["StockTransferLine"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="StockTransferLine.id"
    )

    __audit_exclude__ = frozenset({"updated_at"})


class StockTransferLine(Base, TenantMixin):
    __tablename__ = "stock_transfer_line"
    __table_args__ = (CheckConstraint("quantity > 0", name="positive_qty"),)

    id: Mapped[IntPK]
    transfer_id: Mapped[int] = mapped_column(ForeignKey("stock_transfer.id", ondelete="CASCADE"))
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id", ondelete="RESTRICT"))
    quantity: Mapped[Quantity] = mapped_column()  # base units


class StockCount(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    """A physical count of one location. Posting turns each variance into an adjustment."""

    __tablename__ = "stock_count"

    id: Mapped[IntPK]
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id", ondelete="RESTRICT"))
    count_date: Mapped[date] = mapped_column(Date)
    status: Mapped[CountStatus] = mapped_column(
        str_enum(CountStatus, "count_status"), default=CountStatus.DRAFT
    )
    note: Mapped[str | None] = mapped_column(String(200))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_by: Mapped[int | None] = mapped_column(Integer)

    lines: Mapped[list["StockCountLine"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="StockCountLine.id"
    )

    __audit_exclude__ = frozenset({"updated_at"})


class StockCountLine(Base, TenantMixin):
    __tablename__ = "stock_count_line"
    __table_args__ = (UniqueConstraint("count_id", "item_id"),)

    id: Mapped[IntPK]
    count_id: Mapped[int] = mapped_column(ForeignKey("stock_count.id", ondelete="CASCADE"))
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id", ondelete="RESTRICT"))
    system_qty: Mapped[Quantity] = mapped_column()  # taken when the count was opened
    counted_qty: Mapped[Quantity | None] = mapped_column()
    variance: Mapped[Decimal | None] = mapped_column(nullable=True)


class StockAdjustment(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    """Stock written up or down for one reason at one location (FM2, docs/FINANCE_REVIEW.md
    F3). An issued document: never deleted or edited (migration 0016). A mistake is fixed by
    another adjustment, so the trail shows both."""

    __tablename__ = "stock_adjustment"
    __table_args__ = (
        UniqueConstraint("tenant_id", "number"),
        Index("ix_stock_adjustment_location_date", "location_id", "adjustment_date"),
    )

    id: Mapped[IntPK]
    number: Mapped[str] = mapped_column(String(20))
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id", ondelete="RESTRICT"))
    adjustment_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[AdjustmentReason] = mapped_column(
        str_enum(AdjustmentReason, "adjustment_reason")
    )
    note: Mapped[str | None] = mapped_column(String(200))
    approval_id: Mapped[int | None] = mapped_column(ForeignKey("approval.id", ondelete="RESTRICT"))

    lines: Mapped[list["StockAdjustmentLine"]] = relationship(
        lazy="selectin", order_by="StockAdjustmentLine.id"
    )

    __audit_exclude__ = frozenset({"updated_at"})


class StockAdjustmentLine(Base, TenantMixin):
    __tablename__ = "stock_adjustment_line"
    __table_args__ = (CheckConstraint("quantity > 0", name="positive_qty"),)

    id: Mapped[IntPK]
    adjustment_id: Mapped[int] = mapped_column(
        ForeignKey("stock_adjustment.id", ondelete="RESTRICT")
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id", ondelete="RESTRICT"))
    direction: Mapped[Direction] = mapped_column(str_enum(Direction, "stock_direction"))
    quantity: Mapped[Quantity] = mapped_column()  # base units
    unit_cost: Mapped[UnitCost] = mapped_column()  # weighted average when posted


class StockWritedown(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    """Stock written down to its net realisable value (FM6, docs/FINANCE_REVIEW.md F12).

    A value-only change: no quantity moves and no input tax is reversed, because the goods are
    still there. An issued document (migration 0020): never deleted, never edited; a later
    write-down of the same item is a new document. Accountant to confirm the treatment (AS 2)."""

    __tablename__ = "stock_writedown"
    __table_args__ = (UniqueConstraint("tenant_id", "number"),)

    id: Mapped[IntPK]
    number: Mapped[str] = mapped_column(String(20))
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id", ondelete="RESTRICT"))
    writedown_date: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(200))

    lines: Mapped[list["StockWritedownLine"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="StockWritedownLine.id"
    )

    __audit_exclude__ = frozenset({"updated_at"})


class StockWritedownLine(Base, TenantMixin):
    __tablename__ = "stock_writedown_line"
    __table_args__ = (CheckConstraint("quantity > 0", name="positive_qty"),)

    id: Mapped[IntPK]
    writedown_id: Mapped[int] = mapped_column(ForeignKey("stock_writedown.id", ondelete="RESTRICT"))
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id", ondelete="RESTRICT"))
    quantity: Mapped[Quantity] = mapped_column()  # all the stock of the item, base units
    old_cost: Mapped[UnitCost] = mapped_column()  # the average cost before
    new_cost: Mapped[UnitCost] = mapped_column()  # the NRV it was written down to
    market_rate: Mapped[UnitCost] = mapped_column()  # the rate the NRV came from
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2))  # quantity x (old - new)
