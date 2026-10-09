"""Owner PIN approvals (G18). The counter asks, the owner types a PIN, the server records who
approved what and why, and the approval is good for one use within ten minutes."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ActorMixin, Audited, Base, IntPK, TenantMixin, TimestampMixin
from app.models.enums import ApprovalAction, str_enum


class Approval(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    __tablename__ = "approval"

    id: Mapped[IntPK]
    action: Mapped[ApprovalAction] = mapped_column(str_enum(ApprovalAction, "approval_action"))
    party_id: Mapped[int | None] = mapped_column(ForeignKey("party.id", ondelete="RESTRICT"))
    reason: Mapped[str] = mapped_column(String(300))
    requested_by: Mapped[int] = mapped_column(Integer)
    approved_by: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    used_ref: Mapped[str | None] = mapped_column(String(40))  # the bill number it was used on

    __audit_exclude__ = frozenset({"updated_at"})
