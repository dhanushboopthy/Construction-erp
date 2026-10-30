"""Duolink's own staff and what they do (Milestone 16, ADR 0012).

Platform admins are not users of any company: they have no tenant_id, sign in only at the admin
subdomain and see companies' counts and statuses, never their books.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPK, TimestampMixin
from app.models.enums import PlatformAction, str_enum


class PlatformAdmin(Base, TimestampMixin):
    __tablename__ = "platform_admin"

    id: Mapped[IntPK]
    email: Mapped[str] = mapped_column(String(200), unique=True)
    full_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlatformSession(Base):
    """Refresh-token sessions of platform admins; same design as AuthSession."""

    __tablename__ = "platform_session"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    admin_id: Mapped[int] = mapped_column(
        ForeignKey("platform_admin.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))


class PlatformAuditLog(Base):
    """Append-only: every sign-in and every change a Duolink admin makes."""

    __tablename__ = "platform_audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    admin_id: Mapped[int | None] = mapped_column(ForeignKey("platform_admin.id"), index=True)
    action: Mapped[PlatformAction] = mapped_column(str_enum(PlatformAction, "platform_action"))
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenant.id"), index=True)
    target_user_id: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    request_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64))


__all__ = ["PlatformAdmin", "PlatformAuditLog", "PlatformSession"]
