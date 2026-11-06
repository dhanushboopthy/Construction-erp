"""Duolink's own staff and what they do (Milestone 16, ADR 0012).

Platform admins are not users of any company: they have no tenant_id, sign in only at the admin
subdomain and see companies' counts and statuses, never their books.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import expression

from app.models.base import Base, IntPK, TimestampMixin
from app.models.enums import (
    BackupJobKind,
    BackupJobStatus,
    BackupKind,
    BackupSource,
    BackupStatus,
    DurationUnit,
    PlatformAction,
    PlatformRole,
    str_enum,
)


class PlatformAdmin(Base, TimestampMixin):
    __tablename__ = "platform_admin"

    id: Mapped[IntPK]
    email: Mapped[str] = mapped_column(String(200), unique=True)
    full_name: Mapped[str] = mapped_column(String(100))
    mobile: Mapped[str | None] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[PlatformRole] = mapped_column(
        str_enum(PlatformRole, "platform_role"),
        default=PlatformRole.SUPPORT,
        server_default=PlatformRole.SUPPORT.value,
    )
    # Set for a temporary password: the admin may only change it until they have.
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=expression.false()
    )
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
    # The staff member an action was done to (M17); target_user_id is a company user.
    target_admin_id: Mapped[int | None] = mapped_column(ForeignKey("platform_admin.id"))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    request_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64))


class PlatformPlan(Base, TimestampMixin):
    """A plan Duolink sells (Milestone 20). Not a company's row: no tenant_id. Companies point
    at it through `tenant.plan_id`; a plan in use is archived, never deleted."""

    __tablename__ = "platform_plan"
    # Only one plan is "popular" at a time.
    __table_args__ = (
        Index(
            "uq_platform_plan_one_popular",
            "is_popular",
            unique=True,
            postgresql_where=text("is_popular"),
        ),
    )

    id: Mapped[IntPK]
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    short_description: Mapped[str] = mapped_column(String(200), default="")
    long_description: Mapped[str] = mapped_column(Text, default="")
    max_users: Mapped[int] = mapped_column(Integer)
    max_locations: Mapped[int] = mapped_column(Integer)
    features: Mapped[list[str]] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_popular: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    prices: Mapped[list["PlatformPlanPrice"]] = relationship(
        back_populates="plan",
        order_by="PlatformPlanPrice.sort_order, PlatformPlanPrice.id",
        cascade="all, delete-orphan",
    )


class PlatformPlanPrice(Base):
    """One way to pay for a plan: a duration and a price in rupees."""

    __tablename__ = "platform_plan_price"
    __table_args__ = (
        UniqueConstraint("plan_id", "duration_value", "duration_unit"),
        CheckConstraint("currency = 'INR'", name="currency_inr"),
    )

    id: Mapped[IntPK]
    plan_id: Mapped[int] = mapped_column(ForeignKey("platform_plan.id"), index=True)
    duration_value: Mapped[int] = mapped_column(Integer)
    duration_unit: Mapped[DurationUnit] = mapped_column(
        str_enum(DurationUnit, "plan_duration_unit")
    )
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    plan: Mapped[PlatformPlan] = relationship(back_populates="prices")


class PlatformMaintenance(Base):
    """The operator's maintenance switch (Milestone 24): one row, kept across restarts until a
    Super Admin turns it off. Platform-only: no tenant_id. A restore's own switch (M25) lives in
    memory instead, so a process that dies mid-restore comes back serving."""

    __tablename__ = "platform_maintenance"
    __table_args__ = (CheckConstraint("id = 1", name="singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=expression.false())
    message: Mapped[str | None] = mapped_column(Text)
    # Who last changed it: a name, not a foreign key, as in WA's PlatformMaintenance.
    changed_by: Mapped[str | None] = mapped_column(String(200))
    enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PlatformBackup(Base):
    """One backup file Duolink holds (Milestone 25): a whole-platform dump or one company's
    archive. Platform-only: the company is named by `company_id`, not `tenant_id`, because no
    company owns the row and a company session must never read it."""

    __tablename__ = "platform_backup"
    __table_args__ = (
        CheckConstraint("kind = 'platform' OR company_id IS NOT NULL", name="company_named"),
        Index("ix_platform_backup_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[BackupKind] = mapped_column(str_enum(BackupKind, "backup_kind"))
    source: Mapped[BackupSource] = mapped_column(str_enum(BackupSource, "backup_source"))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("tenant.id"), index=True)
    file_name: Mapped[str] = mapped_column(String(200), unique=True)
    # A platform backup also has a files archive beside the dump (erp-files-<stamp>.tar.gz).
    files_name: Mapped[str | None] = mapped_column(String(200))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64))
    schema_revision: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[BackupStatus] = mapped_column(
        str_enum(BackupStatus, "backup_status"), default=BackupStatus.RUNNING
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_admin_id: Mapped[int | None] = mapped_column(ForeignKey("platform_admin.id"))
    protected: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=expression.false()
    )
    note: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)


class PlatformBackupJob(Base):
    """A long backup or restore, so the page can poll it (Milestone 25)."""

    __tablename__ = "platform_backup_job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[BackupJobKind] = mapped_column(str_enum(BackupJobKind, "backup_job_kind"))
    status: Mapped[BackupJobStatus] = mapped_column(
        str_enum(BackupJobStatus, "backup_job_status"), default=BackupJobStatus.QUEUED
    )
    company_id: Mapped[int | None] = mapped_column(ForeignKey("tenant.id"), index=True)
    # The archive a restore reads, or the backup a backup job made.
    backup_id: Mapped[int | None] = mapped_column(ForeignKey("platform_backup.id"))
    # The protected copy a restore took first.
    safety_backup_id: Mapped[int | None] = mapped_column(ForeignKey("platform_backup.id"))
    requested_by_admin_id: Mapped[int | None] = mapped_column(ForeignKey("platform_admin.id"))
    step: Mapped[str | None] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlatformBackupSchedule(Base):
    """When the nightly backup runs and how many copies are kept: one row, read by
    scripts/backup-loop.sh through `python -m app.scripts.backup_schedule`."""

    __tablename__ = "platform_backup_schedule"
    __table_args__ = (CheckConstraint("id = 1", name="singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False, default=1)
    daily_time: Mapped[str] = mapped_column(String(5), default="02:30", server_default="02:30")
    keep_daily: Mapped[int] = mapped_column(Integer, default=30, server_default="30")
    keep_weekly: Mapped[int] = mapped_column(Integer, default=8, server_default="8")
    keep_monthly: Mapped[int] = mapped_column(Integer, default=12, server_default="12")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by_admin_id: Mapped[int | None] = mapped_column(ForeignKey("platform_admin.id"))


__all__ = [
    "PlatformAdmin",
    "PlatformAuditLog",
    "PlatformBackup",
    "PlatformBackupJob",
    "PlatformBackupSchedule",
    "PlatformMaintenance",
    "PlatformPlan",
    "PlatformPlanPrice",
    "PlatformSession",
]
