"""Support tickets between a company and Duolink (Milestone 22, ADR 0013).

Both tables belong to a company (`tenant_id`, row-level security, platform policy). The company
writes its tickets to Duolink, so the admin may read their subjects and messages. A message is
append-only: the database refuses UPDATE and DELETE. There is no amount anywhere.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPK, TenantMixin, TimestampMixin
from app.models.enums import (
    AuthorKind,
    SupportCategory,
    SupportPriority,
    SupportStatus,
    str_enum,
)


class SupportTicket(Base, TenantMixin, TimestampMixin):
    __tablename__ = "support_ticket"
    __table_args__ = (
        Index("uq_support_ticket_tenant_number", "tenant_id", "number", unique=True),
        Index("ix_support_ticket_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[IntPK]
    number: Mapped[str] = mapped_column(String(20))  # T-000012, per company
    subject: Mapped[str] = mapped_column(String(200))
    category: Mapped[SupportCategory] = mapped_column(str_enum(SupportCategory, "support_category"))
    priority: Mapped[SupportPriority] = mapped_column(
        str_enum(SupportPriority, "support_priority"), default=SupportPriority.NORMAL
    )
    status: Mapped[SupportStatus] = mapped_column(
        str_enum(SupportStatus, "support_status"), default=SupportStatus.OPEN
    )
    raised_by_user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), index=True)
    assigned_admin_id: Mapped[int | None] = mapped_column(ForeignKey("platform_admin.id"))
    last_reply_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # When someone at the company, and when a Duolink admin, last opened the thread: a message
    # newer than this is unread by that side.
    company_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    admin_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SupportMessage(Base, TenantMixin):
    """Append-only."""

    __tablename__ = "support_message"
    __table_args__ = (
        CheckConstraint(
            "(author_kind = 'company_user' AND author_user_id IS NOT NULL "
            "AND author_admin_id IS NULL) OR "
            "(author_kind = 'platform_admin' AND author_admin_id IS NOT NULL "
            "AND author_user_id IS NULL)",
            name="author_matches_kind",
        ),
    )

    id: Mapped[IntPK]
    ticket_id: Mapped[int] = mapped_column(ForeignKey("support_ticket.id"), index=True)
    body: Mapped[str] = mapped_column(Text)
    author_kind: Mapped[AuthorKind] = mapped_column(str_enum(AuthorKind, "support_author_kind"))
    author_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("app_user.id"))
    author_admin_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("platform_admin.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["SupportMessage", "SupportTicket"]
