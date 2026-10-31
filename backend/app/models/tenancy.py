"""Companies using the ERP (ADR 0011). Every business table points here through `tenant_id`."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IntPK, TimestampMixin
from app.models.enums import TenantStatus, str_enum
from app.models.platform import PlatformPlan


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
    # The plan Duolink sold (Milestone 20); a row of the catalogue, never deleted while used.
    plan_id: Mapped[int] = mapped_column(ForeignKey("platform_plan.id"), index=True)
    plan: Mapped[PlatformPlan] = relationship(lazy="joined")
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Blank means the plan's limit (Milestone 16).
    max_users: Mapped[int | None] = mapped_column(Integer)
    max_locations: Mapped[int | None] = mapped_column(Integer)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspended_reason: Mapped[str | None] = mapped_column(Text)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_reason: Mapped[str | None] = mapped_column(Text)
    # Duolink's own record of its customer (Milestone 18). The seller's legal details that print
    # on bills stay in shop_settings; these are who to call and where the company is.
    owner_name: Mapped[str | None] = mapped_column(String(100))
    owner_email: Mapped[str | None] = mapped_column(String(200))
    owner_mobile: Mapped[str | None] = mapped_column(String(20))
    city: Mapped[str | None] = mapped_column(String(100))
    state_code: Mapped[str | None] = mapped_column(String(2))
    notes: Mapped[str | None] = mapped_column(Text)  # internal: Duolink staff only
    # When anyone at the company last made a request; written at most once a minute.
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


__all__ = ["Tenant"]
