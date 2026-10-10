"""Bad-debt write-offs (FM5, docs/FINANCE_REVIEW.md F9).

A write-off is an issued document: never deleted, its figures never edited (triggers in
migration 0019). It credits the customer's receivable account and has no GST effect, so it
is not a credit note. A debt that is paid later is an ordinary receipt."""

from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ActorMixin, Audited, Base, IntPK, Money, TenantMixin, TimestampMixin


class BadDebtWriteoff(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    __tablename__ = "bad_debt_writeoff"
    __table_args__ = (
        UniqueConstraint("tenant_id", "number"),
        CheckConstraint("amount > 0", name="positive_amount"),
        Index("ix_bad_debt_writeoff_party", "party_id", "writeoff_date"),
    )

    id: Mapped[IntPK]
    number: Mapped[str] = mapped_column(String(20))
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id", ondelete="RESTRICT"))
    party_id: Mapped[int] = mapped_column(ForeignKey("party.id", ondelete="RESTRICT"))
    writeoff_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Money] = mapped_column()
    balance_before: Mapped[Money] = mapped_column()  # what the customer owed just before
    reason: Mapped[str] = mapped_column(String(200))

    __audit_exclude__ = frozenset({"updated_at"})
