"""Stock transfers between locations and physical stock counts (Milestone 4)."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    ActorMixin,
    Audited,
    Base,
    IntPK,
    Quantity,
    TenantMixin,
    TimestampMixin,
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
