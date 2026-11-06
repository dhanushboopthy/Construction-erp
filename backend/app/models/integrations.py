"""Duolink's shared integrations (Milestone 27, ADR 0013 point 7).

- `platform_integration`: one row per kind (GSP, GSTIN lookup), Duolink's own provider account.
  Platform-only: no company owns it. Credentials are a Fernet token (`app/core/crypto.py`);
  only their last 4 characters are kept readable, and no API ever returns more.
- `gstin_cache`: public registry answers, shared by every company. Platform-only.
- `integration_call`: one row per call, for counting. It carries the company (blank for a
  Duolink admin's own call, such as a connection test) and never a request or response body.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPK, TimestampMixin
from app.models.enums import (
    IntegrationKind,
    IntegrationOutcome,
    IntegrationProvider,
    IntegrationStatus,
    str_enum,
)

# Until Duolink sets its own (a decision to confirm in the M27 pull request).
DEFAULT_DAILY_LIMIT = 50
DEFAULT_MONTHLY_LIMIT = 500
DEFAULT_WARN_AT_PERCENT = 80
DEFAULT_CACHE_HOURS = 168  # a week


class PlatformIntegration(Base, TimestampMixin):
    __tablename__ = "platform_integration"

    id: Mapped[IntPK]
    kind: Mapped[IntegrationKind] = mapped_column(
        str_enum(IntegrationKind, "integration_kind"), unique=True
    )
    # Blank until a Super Admin connects it; then the environment is no longer used.
    provider: Mapped[IntegrationProvider | None] = mapped_column(
        str_enum(IntegrationProvider, "integration_provider")
    )
    base_url: Mapped[str] = mapped_column(String(300), default="", server_default="")
    credentials: Mapped[str | None] = mapped_column(Text)  # Fernet token of a JSON object
    key_last4: Mapped[str | None] = mapped_column(String(4))
    status: Mapped[IntegrationStatus] = mapped_column(
        str_enum(IntegrationStatus, "integration_status"),
        default=IntegrationStatus.NOT_CONNECTED,
        server_default=IntegrationStatus.NOT_CONNECTED.value,
    )
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    connected_by: Mapped[int | None] = mapped_column(ForeignKey("platform_admin.id"))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_message: Mapped[str | None] = mapped_column(String(200))
    daily_limit: Mapped[int] = mapped_column(
        Integer, default=DEFAULT_DAILY_LIMIT, server_default=str(DEFAULT_DAILY_LIMIT)
    )
    monthly_limit: Mapped[int] = mapped_column(
        Integer, default=DEFAULT_MONTHLY_LIMIT, server_default=str(DEFAULT_MONTHLY_LIMIT)
    )
    warn_at_percent: Mapped[int] = mapped_column(
        Integer, default=DEFAULT_WARN_AT_PERCENT, server_default=str(DEFAULT_WARN_AT_PERCENT)
    )
    cache_hours: Mapped[int] = mapped_column(
        Integer, default=DEFAULT_CACHE_HOURS, server_default=str(DEFAULT_CACHE_HOURS)
    )


class GstinCache(Base):
    __tablename__ = "gstin_cache"

    gstin: Mapped[str] = mapped_column(String(15), primary_key=True)
    legal_name: Mapped[str] = mapped_column(String(200))
    trade_name: Mapped[str] = mapped_column(String(200), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    state_code: Mapped[str] = mapped_column(String(2))
    status: Mapped[str] = mapped_column(String(30))  # as the registry says: Active, Cancelled
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IntegrationCall(Base):
    __tablename__ = "integration_call"
    __table_args__ = (
        Index("ix_integration_call_tenant_kind_at", "tenant_id", "kind", "at"),
        Index("ix_integration_call_kind_at", "kind", "at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Blank for a Duolink admin's own call (connection test, a lookup while onboarding).
    tenant_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tenant.id"))
    kind: Mapped[IntegrationKind] = mapped_column(str_enum(IntegrationKind, "integration_kind"))
    operation: Mapped[str] = mapped_column(String(40))  # generate_eway, lookup_gstin, test, ...
    outcome: Mapped[IntegrationOutcome] = mapped_column(
        str_enum(IntegrationOutcome, "integration_outcome")
    )
    error_code: Mapped[str | None] = mapped_column(String(40))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


__all__ = ["GstinCache", "IntegrationCall", "PlatformIntegration"]
