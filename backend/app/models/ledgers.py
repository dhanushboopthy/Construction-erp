"""Append-only ledgers. Stock and balances are derived from these rows, never stored as
editable numbers (ADR 0003). Database triggers reject UPDATE and DELETE (migration 0003)."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Money, Quantity, TenantMixin, UnitCost
from app.models.enums import LedgerAccount, PartyRef, StockRef, str_enum


class StockLedger(Base, TenantMixin):
    """Quantity in or out of one item at one location, at a cost per base unit."""

    __tablename__ = "stock_ledger"
    __table_args__ = (
        CheckConstraint("qty_in >= 0 AND qty_out >= 0", name="non_negative"),
        CheckConstraint("(qty_in > 0) <> (qty_out > 0)", name="one_direction"),
        Index("ix_stock_ledger_item_location", "item_id", "location_id", "entry_date"),
        Index("ix_stock_ledger_ref", "ref_type", "ref_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id", ondelete="RESTRICT"))
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id", ondelete="RESTRICT"))
    entry_date: Mapped[date] = mapped_column(Date)
    qty_in: Mapped[Quantity] = mapped_column(default=Decimal("0"))
    qty_out: Mapped[Quantity] = mapped_column(default=Decimal("0"))
    unit_cost: Mapped[UnitCost] = mapped_column()
    ref_type: Mapped[StockRef] = mapped_column(str_enum(StockRef, "stock_ref"))
    ref_id: Mapped[int | None] = mapped_column(Integer)
    narration: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[int | None] = mapped_column(Integer)


class PartyLedger(Base, TenantMixin):
    """Money between us and one party. Receivable: bills are debits. Payable: bills are credits."""

    __tablename__ = "party_ledger"
    __table_args__ = (
        CheckConstraint("debit >= 0 AND credit >= 0", name="non_negative"),
        CheckConstraint("(debit > 0) <> (credit > 0)", name="one_side"),
        Index("ix_party_ledger_party", "party_id", "account", "entry_date"),
        Index("ix_party_ledger_ref", "ref_type", "ref_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    party_id: Mapped[int] = mapped_column(ForeignKey("party.id", ondelete="RESTRICT"))
    site_id: Mapped[int | None] = mapped_column(ForeignKey("site.id", ondelete="RESTRICT"))
    account: Mapped[LedgerAccount] = mapped_column(str_enum(LedgerAccount, "ledger_account"))
    entry_date: Mapped[date] = mapped_column(Date)
    ref_type: Mapped[PartyRef] = mapped_column(str_enum(PartyRef, "party_ref"))
    ref_id: Mapped[int | None] = mapped_column(Integer)
    doc_no: Mapped[str | None] = mapped_column(String(20))
    # A payment aimed at one bill (its number); blank means oldest bill first.
    applies_to: Mapped[str | None] = mapped_column(String(20))
    debit: Mapped[Money] = mapped_column(default=Decimal("0"))
    credit: Mapped[Money] = mapped_column(default=Decimal("0"))
    narration: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[int | None] = mapped_column(Integer)
