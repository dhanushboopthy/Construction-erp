"""Names of the ledgers in the accountant's Tally (FM4, docs/FINANCE_REVIEW.md F5).

Only names that differ from the defaults in domain/tally.py are stored, one row per purpose.
The purpose is a ledger purpose ("sales", "output_cgst", ...) or "company", the exact company
name Tally imports into."""

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ActorMixin, Audited, Base, IntPK, TenantMixin, TimestampMixin


class TallyLedger(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    __tablename__ = "tally_ledger"
    __table_args__ = (UniqueConstraint("tenant_id", "purpose"),)

    id: Mapped[IntPK]
    purpose: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(100))

    __audit_exclude__ = frozenset({"updated_at"})
