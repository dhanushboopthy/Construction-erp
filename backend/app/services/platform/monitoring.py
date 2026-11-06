"""What Duolink watches: how many companies and users, who is signing in, which trials end soon,
and what Duolink's own admins did. Counts and events only (ADR 0012)."""

import csv
import io
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session, aliased

from app.core.errors import BusinessRuleError
from app.domain import platform_health as health_rules
from app.domain.plans import ENDING_SOON_DAYS
from app.models.audit import AuditLog
from app.models.auth import AuthSession
from app.models.enums import AuditAction, PlatformAction, TenantStatus
from app.models.platform import PlatformAdmin, PlatformAuditLog
from app.models.setup import AppUser
from app.models.tenancy import Tenant
from app.schemas.platform import OverviewOut, PlatformAuditRow, SignInEvent, TrialEnding
from app.services.platform.audit import record

SIGN_IN_ACTIONS = (AuditAction.LOGIN, AuditAction.LOGIN_FAILED, AuditAction.TOKEN_REUSE)


def _now() -> datetime:
    return datetime.now(UTC)


def _count_events(db: Session, action: AuditAction, since: datetime) -> int:
    return db.execute(
        select(func.count()).where(AuditLog.action == action, AuditLog.at >= since)
    ).scalar_one()


def overview(db: Session) -> OverviewOut:
    now = _now()
    day, week = now - timedelta(days=1), now - timedelta(days=7)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    by_status = dict.fromkeys(TenantStatus, 0)
    for status, count in db.execute(
        select(Tenant.status, func.count()).group_by(Tenant.status)
    ).all():
        by_status[status] = count

    ending = db.scalars(
        select(Tenant)
        .where(
            Tenant.status == TenantStatus.TRIAL,
            Tenant.trial_ends_at.is_not(None),
            Tenant.trial_ends_at <= now + timedelta(days=ENDING_SOON_DAYS),
        )
        .order_by(Tenant.trial_ends_at)
    )
    return OverviewOut(
        tenants_total=sum(by_status.values()),
        tenants_by_status=by_status,
        new_tenants_this_month=db.execute(
            select(func.count()).where(Tenant.created_at >= month_start)
        ).scalar_one(),
        active_users=db.execute(
            select(func.count()).where(AppUser.is_active.is_(True))
        ).scalar_one(),
        open_sessions=db.execute(
            select(func.count()).where(
                AuthSession.revoked_at.is_(None), AuthSession.expires_at > now
            )
        ).scalar_one(),
        sign_ins_24h=_count_events(db, AuditAction.LOGIN, day),
        sign_ins_7d=_count_events(db, AuditAction.LOGIN, week),
        failed_sign_ins_24h=_count_events(db, AuditAction.LOGIN_FAILED, day),
        failed_sign_ins_7d=_count_events(db, AuditAction.LOGIN_FAILED, week),
        trials_ending=[
            TrialEnding(id=t.id, slug=t.slug, name=t.name, trial_ends_at=t.trial_ends_at)
            for t in ending
            if t.trial_ends_at is not None
        ],
    )


def _bounds(
    date_from: date | None, date_to: date | None
) -> tuple[datetime | None, datetime | None]:
    try:
        return health_rules.day_bounds(date_from, date_to)
    except health_rules.PlatformRuleError as exc:
        raise BusinessRuleError(str(exc), code=exc.code, field="date_to") from exc


def sign_ins(
    db: Session,
    *,
    tenant_id: int | None = None,
    action: AuditAction | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[SignInEvent], int]:
    """Sign-ins, failed sign-ins and reused (likely stolen) tokens, newest first. Dates are
    whole days in India, both ends included (Milestone 24)."""
    filters: list[ColumnElement[bool]] = [
        AuditLog.action.in_([action] if action else SIGN_IN_ACTIONS)
    ]
    if tenant_id is not None:
        filters.append(AuditLog.tenant_id == tenant_id)
    start, end = _bounds(date_from, date_to)
    if start is not None:
        filters.append(AuditLog.at >= start)
    if end is not None:
        filters.append(AuditLog.at < end)
    total = db.execute(select(func.count()).select_from(AuditLog).where(*filters)).scalar_one()
    rows = db.execute(
        select(AuditLog, Tenant.slug, AppUser.username)
        .join(Tenant, Tenant.id == AuditLog.tenant_id)
        .outerjoin(AppUser, AppUser.id == AuditLog.user_id)
        .where(*filters)
        .order_by(AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    events = [
        SignInEvent(
            at=log.at,
            tenant_id=log.tenant_id,
            tenant_slug=slug,
            # A failed sign-in for an unknown name logs the name that was typed.
            username=(log.changes or {}).get("username") or username,
            action=log.action.value,
            ip=log.ip,
        )
        for log, slug, username in rows
    ]
    return events, total


@dataclass(frozen=True)
class AuditFilters:
    """The Audit page's filters (Milestone 24); the CSV export takes exactly the same ones."""

    tenant_id: int | None = None
    admin_id: int | None = None
    action: PlatformAction | None = None
    date_from: date | None = None
    date_to: date | None = None

    def as_details(self) -> dict[str, object]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


def _admin_filters(filters: AuditFilters) -> list[ColumnElement[bool]]:
    where: list[ColumnElement[bool]] = []
    if filters.tenant_id is not None:
        where.append(PlatformAuditLog.tenant_id == filters.tenant_id)
    if filters.admin_id is not None:
        where.append(PlatformAuditLog.admin_id == filters.admin_id)
    if filters.action:
        where.append(PlatformAuditLog.action == filters.action)
    start, end = _bounds(filters.date_from, filters.date_to)
    if start is not None:
        where.append(PlatformAuditLog.at >= start)
    if end is not None:
        where.append(PlatformAuditLog.at < end)
    return where


def _admin_rows(
    db: Session, where: list[ColumnElement[bool]], *, limit: int, offset: int
) -> list[PlatformAuditRow]:
    target = aliased(PlatformAdmin)
    rows = db.execute(
        select(PlatformAuditLog, PlatformAdmin.email, Tenant.slug, target.email)
        .outerjoin(PlatformAdmin, PlatformAdmin.id == PlatformAuditLog.admin_id)
        .outerjoin(target, target.id == PlatformAuditLog.target_admin_id)
        .outerjoin(Tenant, Tenant.id == PlatformAuditLog.tenant_id)
        .where(*where)
        .order_by(PlatformAuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [
        PlatformAuditRow(
            id=log.id,
            at=log.at,
            admin_email=email,
            action=log.action,
            tenant_slug=slug,
            target_user_id=log.target_user_id,
            target_admin_email=target_email,
            details=log.details,
            ip=log.ip,
        )
        for log, email, slug, target_email in rows
    ]


def admin_actions(
    db: Session,
    filters: AuditFilters | None = None,
    *,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[PlatformAuditRow], int]:
    """What Duolink's admins did, newest first."""
    where = _admin_filters(filters or AuditFilters())
    total = db.execute(
        select(func.count()).select_from(PlatformAuditLog).where(*where)
    ).scalar_one()
    return _admin_rows(db, where, limit=limit, offset=offset), total


EXPORT_MAX_ROWS = 50_000
CSV_COLUMNS = (
    "id",
    "at",
    "admin",
    "action",
    "company",
    "target_user_id",
    "target_admin",
    "details",
    "ip",
)


def export_admin_actions(db: Session, filters: AuditFilters, admin_id: int) -> tuple[str, int]:
    """The filtered admin actions as CSV, one row per audited action, newest first, with the
    same filters as the screen (Super Admin). The export itself is audited, after the rows are
    read, so it is not in its own file."""
    entries = _admin_rows(db, _admin_filters(filters), limit=EXPORT_MAX_ROWS, offset=0)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for e in entries:
        writer.writerow(
            [
                health_rules.csv_cell(cell)
                for cell in (
                    e.id,
                    e.at.isoformat(),
                    e.admin_email,
                    e.action.value,
                    e.tenant_slug,
                    e.target_user_id,
                    e.target_admin_email,
                    json.dumps(e.details, sort_keys=True) if e.details else "",
                    e.ip,
                )
            ]
        )
    record(
        db,
        PlatformAction.AUDIT_EXPORT,
        admin_id,
        tenant_id=filters.tenant_id,
        details={"filters": filters.as_details(), "rows": len(entries)},
    )
    db.commit()
    return out.getvalue(), len(entries)
