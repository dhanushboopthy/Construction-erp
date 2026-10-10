"""Bank accounts and imported statements (FM7, docs/FINANCE_REVIEW.md F16).

A statement is an issued record: the bank's own lines, never deleted and never edited (triggers
in migration 0021). Whether a line matches a receipt is worked out when the report is read, so a
receipt entered late still finds its line."""

from datetime import date

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ActorMixin, Audited, Base, IntPK, Money, TenantMixin, TimestampMixin


class BankAccount(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    """An account that receives UPI and transfers or takes the cash deposits."""

    __tablename__ = "bank_account"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)

    id: Mapped[IntPK]
    name: Mapped[str] = mapped_column(String(60))
    account_no_last4: Mapped[str | None] = mapped_column(String(4))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __audit_exclude__ = frozenset({"updated_at"})


class BankStatement(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    """One uploaded CSV."""

    __tablename__ = "bank_statement"
    __table_args__ = (UniqueConstraint("tenant_id", "bank_account_id", "file_sha256"),)

    id: Mapped[IntPK]
    bank_account_id: Mapped[int] = mapped_column(ForeignKey("bank_account.id", ondelete="RESTRICT"))
    filename: Mapped[str] = mapped_column(String(200))
    file_sha256: Mapped[str] = mapped_column(String(64))
    from_date: Mapped[date] = mapped_column(Date)
    to_date: Mapped[date] = mapped_column(Date)
    row_count: Mapped[int] = mapped_column(Integer)  # rows in the file
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)  # already imported before
    closing_balance: Mapped[Money | None] = mapped_column()

    __audit_exclude__ = frozenset({"updated_at"})


class BankStatementLine(Base, TenantMixin):
    __tablename__ = "bank_statement_line"
    __table_args__ = (
        CheckConstraint("debit >= 0 AND credit >= 0 AND debit + credit > 0", name="one_amount"),
        Index("ix_bank_statement_line_date", "line_date"),
    )

    id: Mapped[IntPK]
    statement_id: Mapped[int] = mapped_column(ForeignKey("bank_statement.id", ondelete="RESTRICT"))
    line_no: Mapped[int] = mapped_column(Integer)
    line_date: Mapped[date] = mapped_column(Date)
    narration: Mapped[str] = mapped_column(String(300), default="")
    reference: Mapped[str] = mapped_column(String(60), default="")
    debit: Mapped[Money] = mapped_column()
    credit: Mapped[Money] = mapped_column()
    balance: Mapped[Money | None] = mapped_column()
