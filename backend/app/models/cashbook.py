"""Cash book (FM1, docs/FINANCE_REVIEW.md F1, F2): expense categories and vouchers for
expenses, bank deposits and withdrawals, and the owner's drawings and capital.

A voucher is an issued document: never deleted, its figures never edited (triggers in
migration 0015). A mistake is undone by a reversal voucher that points at the original."""

from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.finance import CashEntryKind, ExpenseNature
from app.models.base import ActorMixin, Audited, Base, IntPK, Money, TenantMixin, TimestampMixin
from app.models.enums import PaymentMode, str_enum


class ExpenseCategory(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    """A head of expense: rent, salaries, loading labour... Its nature decides where it falls
    in the profit and loss and whether it counts as a fixed cost for break-even."""

    __tablename__ = "expense_category"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)

    id: Mapped[IntPK]
    name: Mapped[str] = mapped_column(String(60))
    nature: Mapped[ExpenseNature] = mapped_column(str_enum(ExpenseNature, "expense_nature"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __audit_exclude__ = frozenset({"updated_at"})


class CashEntry(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    """One cash-book voucher at one shop on one day."""

    __tablename__ = "cash_entry"
    __table_args__ = (
        UniqueConstraint("tenant_id", "number"),
        UniqueConstraint("reverses_id"),  # an entry is reversed at most once
        CheckConstraint("amount > 0", name="positive_amount"),
        CheckConstraint(
            "(kind = 'expense') = (category_id IS NOT NULL)", name="category_for_expenses"
        ),
        Index("ix_cash_entry_location_date", "location_id", "entry_date"),
    )

    id: Mapped[IntPK]
    number: Mapped[str] = mapped_column(String(20))
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id", ondelete="RESTRICT"))
    entry_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[CashEntryKind] = mapped_column(str_enum(CashEntryKind, "cash_entry_kind"))
    mode: Mapped[PaymentMode] = mapped_column(str_enum(PaymentMode, "payment_mode"))
    amount: Mapped[Money] = mapped_column()
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("expense_category.id", ondelete="RESTRICT")
    )
    paid_to: Mapped[str | None] = mapped_column(String(100))
    reference: Mapped[str | None] = mapped_column(String(60))  # UPI or bank reference
    note: Mapped[str | None] = mapped_column(String(200))
    reverses_id: Mapped[int | None] = mapped_column(
        ForeignKey("cash_entry.id", ondelete="RESTRICT")
    )
    approval_id: Mapped[int | None] = mapped_column(ForeignKey("approval.id", ondelete="RESTRICT"))

    __audit_exclude__ = frozenset({"updated_at"})
