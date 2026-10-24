"""Companies using the ERP (ADR 0011). Every business table points here through `tenant_id`."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPK, TimestampMixin
from app.models.enums import TenantPlan, TenantStatus, str_enum


class Tenant(Base, TimestampMixin):
    """One company. The slug is its subdomain: acme.duolink.app. Never deleted: a company that
    leaves is cancelled, because its GST books must be kept."""

    __tablename__ = "tenant"

    id: Mapped[IntPK]
    slug: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[TenantStatus] = mapped_column(
        str_enum(TenantStatus, "tenant_status"), default=TenantStatus.TRIAL
    )
    plan: Mapped[TenantPlan] = mapped_column(
        str_enum(TenantPlan, "tenant_plan"), default=TenantPlan.TRIAL
    )
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Blank means the plan's default limit (Milestone 16).
    max_users: Mapped[int | None] = mapped_column(Integer)
    max_locations: Mapped[int | None] = mapped_column(Integer)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspended_reason: Mapped[str | None] = mapped_column(Text)


__all__ = ["Tenant"]
