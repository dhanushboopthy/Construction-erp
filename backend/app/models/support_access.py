"""Owner-granted support access, "Login as Company" with consent (Milestone 23, ADR 0013).

All three tables belong to the company (`tenant_id`, row-level security, platform policy):

- `support_access_grant`: the owner's consent, for a fixed time, revocable at once. At most one
  is live per company; a new one revokes the old.
- `support_session`: one visit by a Duolink Super Admin under a grant, with its request count.
- `support_session_event`: the method and path of every request of a session (never a body or
  a query string). Append-only: the database refuses UPDATE and DELETE. Kept at least a year.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import expression

from app.models.base import ActorMixin, Audited, Base, IntPK, TenantMixin, TimestampMixin
from app.models.enums import SupportSessionEnd, str_enum


class SupportAccessGrant(Base, Audited, TenantMixin, TimestampMixin, ActorMixin):
    __tablename__ = "support_access_grant"
    __table_args__ = (Index("ix_support_access_grant_tenant_ends", "tenant_id", "ends_at"),)

    id: Mapped[IntPK]
    granted_by_user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"))  # an owner
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    include_costs: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=expression.false()
    )
    reason: Mapped[str] = mapped_column(String(300))
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("support_ticket.id"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))


class SupportSession(Base, TenantMixin):
    """Written by the platform service (enter) and the support gate (count, end); the company's
    audit log gets `support_enter` and `support_exit` events instead of row diffs."""

    __tablename__ = "support_session"
    __table_args__ = (Index("ix_support_session_tenant_started", "tenant_id", "started_at"),)

    id: Mapped[IntPK]
    grant_id: Mapped[int] = mapped_column(ForeignKey("support_access_grant.id"), index=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("platform_admin.id"), index=True)
    reason: Mapped[str] = mapped_column(String(300))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # the token's expiry
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_reason: Mapped[SupportSessionEnd | None] = mapped_column(
        str_enum(SupportSessionEnd, "support_session_end")
    )
    request_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class SupportSessionEvent(Base, TenantMixin):
    """Append-only."""

    __tablename__ = "support_session_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("support_session.id"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    method: Mapped[str] = mapped_column(String(8))
    path: Mapped[str] = mapped_column(String(300))
    refused: Mapped[bool] = mapped_column(Boolean, default=False)  # a write, answered 403


__all__ = ["SupportAccessGrant", "SupportSession", "SupportSessionEvent"]
