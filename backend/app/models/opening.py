"""Opening balances entered once at go-live (Milestone 3).

A row is a draft until the owner posts it; posting writes the stock or party ledger and locks
the row. Mistakes after posting are corrected with a stock count or a credit/debit note."""

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
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
from app.models.enums import OpeningKind, OpeningStatus, str_enum


class OpeningBalance(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    __tablename__ = "opening_balance"
    __table_args__ = (
        CheckConstraint(
            "(kind = 'stock' AND item_id IS NOT NULL AND location_id IS NOT NULL"
            " AND quantity > 0 AND unit_cost IS NOT NULL AND party_id IS NULL AND amount IS NULL)"
            " OR (kind <> 'stock' AND party_id IS NOT NULL AND amount > 0"
            " AND item_id IS NULL AND location_id IS NULL AND quantity IS NULL)",
            name="shape_by_kind",
        ),
        # One opening figure per item and location, and per party, site and kind.
        Index(
            "uq_opening_stock",
            "item_id",
            "location_id",
            unique=True,
            postgresql_where=text("kind = 'stock'"),
        ),
        Index(
            "uq_opening_money",
            "party_id",
            text("coalesce(site_id, 0)"),
            "kind",
            unique=True,
            postgresql_where=text("kind <> 'stock'"),
        ),
    )

    id: Mapped[IntPK]
    kind: Mapped[OpeningKind] = mapped_column(str_enum(OpeningKind, "opening_kind"))
    status: Mapped[OpeningStatus] = mapped_column(
        str_enum(OpeningStatus, "opening_status"), default=OpeningStatus.DRAFT
    )
    as_of: Mapped[date] = mapped_column(Date)
    item_id: Mapped[int | None] = mapped_column(ForeignKey("item.id", ondelete="RESTRICT"))
    location_id: Mapped[int | None] = mapped_column(ForeignKey("location.id", ondelete="RESTRICT"))
    quantity: Mapped[Quantity | None] = mapped_column()
    unit_cost: Mapped[UnitCost | None] = mapped_column()
    party_id: Mapped[int | None] = mapped_column(ForeignKey("party.id", ondelete="RESTRICT"))
    site_id: Mapped[int | None] = mapped_column(ForeignKey("site.id", ondelete="RESTRICT"))
    amount: Mapped[Money | None] = mapped_column()
    note: Mapped[str | None] = mapped_column(String(200))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_by: Mapped[int | None] = mapped_column(Integer)

    __audit_exclude__ = frozenset({"updated_at"})
