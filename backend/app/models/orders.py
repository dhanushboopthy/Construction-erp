"""Purchase orders, goods received, cement lots on sales, and the lost-sales log (FM10,
docs/FINANCE_REVIEW.md F25, F26).

Orders, receipts and lost-sales entries are permanent records (triggers in migration 0022): a
mistake is a new document or entry. A goods receipt records what the weighbridge or the count
showed; it moves no stock, because stock enters with the supplier's bill."""

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
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


class PurchaseOrder(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    __tablename__ = "purchase_order"
    __table_args__ = (
        UniqueConstraint("tenant_id", "number"),
        Index("ix_purchase_order_supplier", "supplier_id", "order_date"),
    )

    id: Mapped[IntPK]
    number: Mapped[str] = mapped_column(String(20))
    supplier_id: Mapped[int] = mapped_column(ForeignKey("party.id", ondelete="RESTRICT"))
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id", ondelete="RESTRICT"))
    order_date: Mapped[date] = mapped_column(Date)
    expected_date: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(200))

    lines: Mapped[list["PurchaseOrderLine"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="PurchaseOrderLine.line_no"
    )

    __audit_exclude__ = frozenset({"updated_at"})


class PurchaseOrderLine(Base, TenantMixin):
    __tablename__ = "purchase_order_line"
    __table_args__ = (
        UniqueConstraint("order_id", "line_no"),
        CheckConstraint("base_qty > 0 AND rate >= 0", name="positive_qty"),
    )

    id: Mapped[IntPK]
    order_id: Mapped[int] = mapped_column(ForeignKey("purchase_order.id", ondelete="RESTRICT"))
    line_no: Mapped[int] = mapped_column(Integer)
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id", ondelete="RESTRICT"))
    unit: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))  # in `unit`
    base_qty: Mapped[Quantity] = mapped_column()
    rate: Mapped[Decimal] = mapped_column(Numeric(14, 4))  # per `unit`, excluding GST (owner only)


class GoodsReceipt(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    __tablename__ = "goods_receipt"
    __table_args__ = (
        UniqueConstraint("tenant_id", "number"),
        Index("ix_goods_receipt_order", "order_id"),
    )

    id: Mapped[IntPK]
    number: Mapped[str] = mapped_column(String(20))
    order_id: Mapped[int] = mapped_column(ForeignKey("purchase_order.id", ondelete="RESTRICT"))
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id", ondelete="RESTRICT"))
    receipt_date: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(200))

    lines: Mapped[list["GoodsReceiptLine"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="GoodsReceiptLine.id"
    )

    __audit_exclude__ = frozenset({"updated_at"})


class GoodsReceiptLine(Base, TenantMixin):
    __tablename__ = "goods_receipt_line"
    __table_args__ = (CheckConstraint("base_qty > 0", name="positive_qty"),)

    id: Mapped[IntPK]
    receipt_id: Mapped[int] = mapped_column(ForeignKey("goods_receipt.id", ondelete="RESTRICT"))
    order_line_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_order_line.id", ondelete="RESTRICT")
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id", ondelete="RESTRICT"))
    unit: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    base_qty: Mapped[Quantity] = mapped_column()


class SalesLineLot(Base, TenantMixin):
    """Which delivery's cement a sale line took (oldest manufacturing week first). A sale line can
    draw from several lots. `mfg_week` is blank for a delivery with no week printed."""

    __tablename__ = "sales_line_lot"
    __table_args__ = (
        CheckConstraint("base_qty > 0", name="positive_qty"),
        Index("ix_sales_line_lot_line", "sales_line_id"),
        Index("ix_sales_line_lot_purchase_line", "purchase_line_id"),
    )

    id: Mapped[IntPK]
    sales_line_id: Mapped[int] = mapped_column(ForeignKey("sales_line.id", ondelete="RESTRICT"))
    purchase_line_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_line.id", ondelete="RESTRICT")
    )
    mfg_week: Mapped[int | None] = mapped_column(Integer)
    mfg_year: Mapped[int | None] = mapped_column(Integer)
    base_qty: Mapped[Quantity] = mapped_column()


class LostSale(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    """A customer asked for something we did not have. One entry per ask; permanent."""

    __tablename__ = "lost_sale"
    __table_args__ = (
        CheckConstraint("base_qty > 0", name="positive_qty"),
        Index("ix_lost_sale_location_date", "location_id", "entry_date"),
    )

    id: Mapped[IntPK]
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id", ondelete="RESTRICT"))
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id", ondelete="RESTRICT"))
    entry_date: Mapped[date] = mapped_column(Date)
    unit: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    base_qty: Mapped[Quantity] = mapped_column()
    note: Mapped[str | None] = mapped_column(String(200))
    # The market rate per base unit on the day, to value the lost sale. Owner only.
    market_rate: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))

    __audit_exclude__ = frozenset({"updated_at"})
