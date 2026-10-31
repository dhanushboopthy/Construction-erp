"""What Duolink watches: how many companies and users, who is signing in, which trials end soon,
and what Duolink's own admins did. Counts and events only (ADR 0012)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session, aliased

from app.domain.plans import ENDING_SOON_DAYS
from app.models.audit import AuditLog
from app.models.auth import AuthSession
from app.models.enums import AuditAction, PlatformAction, TenantStatus
from app.models.platform import PlatformAdmin, PlatformAuditLog
from app.models.setup import AppUser
from app.models.tenancy import Tenant
from app.schemas.platform import OverviewOut, PlatformAuditRow, SignInEvent, TrialEnding

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


def sign_ins(
    db: Session,
    *,
    tenant_id: int | None = None,
    action: AuditAction | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[SignInEvent], int]:
    """Sign-ins, failed sign-ins and reused (likely stolen) tokens, newest first."""
    filters: list[ColumnElement[bool]] = [
        AuditLog.action.in_([action] if action else SIGN_IN_ACTIONS)
    ]
    if tenant_id is not None:
        filters.append(AuditLog.tenant_id == tenant_id)
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


def admin_actions(
    db: Session,
    *,
    tenant_id: int | None = None,
    action: PlatformAction | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[PlatformAuditRow], int]:
    filters = []
    if tenant_id is not None:
        filters.append(PlatformAuditLog.tenant_id == tenant_id)
    if action:
        filters.append(PlatformAuditLog.action == action)
    total = db.execute(
        select(func.count()).select_from(PlatformAuditLog).where(*filters)
    ).scalar_one()
    target = aliased(PlatformAdmin)
    rows = db.execute(
        select(PlatformAuditLog, PlatformAdmin.email, Tenant.slug, target.email)
        .outerjoin(PlatformAdmin, PlatformAdmin.id == PlatformAuditLog.admin_id)
        .outerjoin(target, target.id == PlatformAuditLog.target_admin_id)
        .outerjoin(Tenant, Tenant.id == PlatformAuditLog.tenant_id)
        .where(*filters)
        .order_by(PlatformAuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    entries = [
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
    return entries, total
