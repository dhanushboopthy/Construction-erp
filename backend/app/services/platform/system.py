"""System health, the notifications bell, maintenance mode and platform settings (Milestone 24).

Health reuses what the readiness check and the company System page already compute (the database
round trip, the migrations check, the backup check, the e-way bill provider) and adds what only
Duolink needs: database size and connections, disk space, the backup marker and counters across
every company. Nothing here carries an amount, a secret or a connection string.
"""

import platform as py_platform
import shutil
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import ColumnElement, func, select, text
from sqlalchemy.orm import Session

from app.core.clock import SHOP_TZ
from app.core.config import StorageProvider, get_settings
from app.core.errors import BusinessRuleError
from app.domain import platform_health as rules
from app.domain.plans import ENDING_SOON_DAYS, MAX_TRIAL_DAYS, TRIAL_DAYS
from app.domain.subscriptions import BANNER_DAYS
from app.models.audit import AuditLog
from app.models.auth import AuthSession
from app.models.enums import PlatformAction
from app.models.platform import PlatformAdmin, PlatformAuditLog
from app.models.setup import AppUser
from app.models.support import SupportTicket
from app.models.support_access import SupportSession
from app.models.tenancy import Tenant
from app.schemas.platform_system import (
    ApiHealth,
    BackupHealth,
    DatabaseHealth,
    DiskHealth,
    HealthCounters,
    LifecycleSettings,
    MaintenanceIn,
    MaintenanceNotice,
    MaintenanceOut,
    NotificationOut,
    NotificationsOut,
    PlatformSettingsOut,
    SecuritySettings,
    SystemHealth,
)
from app.services import maintenance as switch_service
from app.services import verify
from app.services.maintenance import MaintenanceSwitch
from app.services.platform import billing
from app.services.platform.audit import record
from app.services.platform.support import OPEN_STATES, ticket_counts

CHANGELOG = Path(__file__).resolve().parents[4] / "CHANGELOG.md"
LAST_SUCCESS = ".last-success"  # written by scripts/backup-loop.sh after a good backup
OFFSITE_SUCCESS = ".offsite-success"  # written by scripts/offsite-sync.sh after a good copy


def _now() -> datetime:
    return datetime.now(UTC)


def _since_midnight(now: datetime) -> datetime:
    return datetime.combine(now.astimezone(SHOP_TZ).date(), datetime.min.time(), SHOP_TZ)


def _marker(folder: str, name: str) -> datetime | None:
    if not folder:
        return None
    try:
        return rules.parse_last_success((Path(folder) / name).read_text(encoding="utf-8"))
    except OSError:
        return None


def _changelog_version() -> str | None:
    try:
        return rules.changelog_version(CHANGELOG.read_text(encoding="utf-8"))
    except OSError:
        return None


# ------------------------------------------------------------------ the parts of health


def _disk(name: str, folder: str | None) -> DiskHealth:
    if not folder or not Path(folder).exists():
        return DiskHealth(
            name=name,
            watched=False,
            total_bytes=None,
            free_bytes=None,
            free_percent=None,
            low=False,
        )
    usage = shutil.disk_usage(folder)
    free = rules.free_percent(usage.total, usage.free)
    return DiskHealth(
        name=name,
        watched=True,
        total_bytes=usage.total,
        free_bytes=usage.free,
        free_percent=free,
        low=free is not None and free < rules.DISK_LOW_FREE_PERCENT,
    )


def disks() -> list[DiskHealth]:
    settings = get_settings()
    files = settings.storage_dir if settings.storage_provider is StorageProvider.LOCAL else None
    return [_disk("backups", settings.backup_dir or None), _disk("files", files)]


def last_backup_at() -> datetime | None:
    """The backup service's own marker, else the newest dump's time (the company System page)."""
    folder = get_settings().backup_dir
    marked = _marker(folder, LAST_SUCCESS)
    if marked is not None:
        return marked
    return verify.backup_check()[1]


def _backup(now: datetime) -> BackupHealth:
    check, _ = verify.backup_check()
    last = last_backup_at()
    return BackupHealth(
        check=check,
        last_success_at=last,
        age_hours=rules.hours_since(last, now),
        stale=bool(get_settings().backup_dir) and rules.backup_is_stale(last, now),
        offsite_synced_at=_marker(get_settings().backup_dir, OFFSITE_SUCCESS),
    )


def _database(db: Session) -> DatabaseHealth:
    started = time.perf_counter_ns()
    db.execute(text("SELECT 1"))
    elapsed_ns = time.perf_counter_ns() - started
    size, connections, version = db.execute(
        text(
            "SELECT pg_database_size(current_database()), "
            "(SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()), "
            "current_setting('server_version')"
        )
    ).one()
    return DatabaseHealth(
        up=True,
        round_trip_ms=(Decimal(elapsed_ns) / Decimal(1_000_000)).quantize(Decimal("0.01")),
        size_bytes=size,
        connections_in_use=connections,
        server_version=version,
        migrations=verify.migrations_check(db),
    )


def _counters(db: Session, now: datetime) -> HealthCounters:
    midnight = _since_midnight(now)

    def count(*where: ColumnElement[bool]) -> int:
        return int(db.execute(select(func.count()).where(*where)).scalar_one())

    return HealthCounters(
        companies=int(db.execute(select(func.count()).select_from(Tenant)).scalar_one()),
        active_users=count(AppUser.is_active.is_(True)),
        open_sessions=count(AuthSession.revoked_at.is_(None), AuthSession.expires_at > now),
        audit_events_today=count(AuditLog.at >= midnight),
        admin_actions_today=count(PlatformAuditLog.at >= midnight),
        open_tickets=count(SupportTicket.status.in_(OPEN_STATES)),
    )


def health(db: Session, *, started_at: datetime, switch: MaintenanceSwitch) -> SystemHealth:
    settings = get_settings()
    now = _now()
    state = switch.state(db)
    return SystemHealth(
        as_of=now,
        api=ApiHealth(
            started_at=started_at,
            uptime_seconds=max(0, int((now - started_at) // timedelta(seconds=1))),
            version=settings.app_version,
            changelog_version=_changelog_version(),
            python_version=py_platform.python_version(),
            environment=settings.app_env.value,
        ),
        database=_database(db),
        disks=disks(),
        backup=_backup(now),
        gsp=verify.gsp_check(),
        counters=_counters(db, now),
        maintenance=MaintenanceNotice(enabled=state.enabled, message=state.message),
    )


# ------------------------------------------------------------------ the bell


def _subscriptions(db: Session, status: str, expiring_within: int | None = None) -> int:
    """The Subscriptions list's own count for these filters, so the bell and the list agree."""
    _, total = billing.list_subscriptions(
        db,
        status=status,
        plan=None,
        expiring_within=expiring_within,
        tenant_id=None,
        search=None,
        limit=1,
        offset=0,
    )
    return total


def _failed_admin_sign_ins(db: Session, now: datetime) -> int:
    return int(
        db.execute(
            select(func.count()).where(
                PlatformAuditLog.action == PlatformAction.LOGIN_FAILED,
                PlatformAuditLog.at >= now - timedelta(hours=24),
            )
        ).scalar_one()
    )


def open_support_sessions(db: Session, now: datetime) -> int:
    """Support sessions never ended whose token has expired (Milestone 23's `support_session`)."""
    return int(
        db.execute(
            select(func.count())
            .select_from(SupportSession)
            .where(SupportSession.ended_at.is_(None), SupportSession.expires_at <= now)
        ).scalar_one()
    )


def signals(db: Session, now: datetime) -> rules.Signals:
    tickets = ticket_counts(db)
    return rules.Signals(
        expiring=_subscriptions(db, "active", rules.EXPIRING_DAYS),
        expired=_subscriptions(db, "expired"),
        trials_ending=_subscriptions(db, "trial", rules.EXPIRING_DAYS),
        new_tickets=tickets.open,
        urgent_tickets=tickets.urgent_open,
        open_support_sessions=open_support_sessions(db, now),
        backups_watched=bool(get_settings().backup_dir),
        last_backup_at=last_backup_at(),
        disks=tuple(
            rules.Disk(d.name, d.total_bytes or 0, d.free_bytes or 0) for d in disks() if d.watched
        ),
        failed_admin_sign_ins=_failed_admin_sign_ins(db, now),
    )


def notifications(db: Session) -> NotificationsOut:
    now = _now()
    items = [
        NotificationOut(id=n.id, level=n.level, title=n.title, body=n.body, link=n.link)
        for n in rules.notifications(signals(db, now), now)
    ]
    return NotificationsOut(count=len(items), items=items)


# ------------------------------------------------------------------ maintenance


def maintenance(db: Session, switch: MaintenanceSwitch) -> MaintenanceOut:
    row = switch_service.read_row(db)
    state = switch.state(db)
    return MaintenanceOut(
        enabled=state.enabled,
        message=state.message,
        cause=state.cause,
        operator_enabled=row.enabled,
        operator_message=row.message,
        changed_by=row.changed_by,
        enabled_at=row.enabled_at,
        updated_at=row.updated_at,
        restoring=switch.restoring,
    )


def set_maintenance(
    db: Session, switch: MaintenanceSwitch, data: MaintenanceIn, admin_id: int
) -> MaintenanceOut:
    """Turn the operator's switch on or off. Audited; takes effect in this process at once and in
    any other within 5 seconds."""
    try:
        message = rules.clean_message(data.message)
    except rules.PlatformRuleError as exc:
        raise BusinessRuleError(str(exc), code=exc.code, field="message") from exc
    admin = db.get(PlatformAdmin, admin_id)
    row = switch_service.read_row(db)
    was = row.enabled
    row.enabled = data.enabled
    row.message = message if data.enabled else row.message
    row.changed_by = admin.full_name if admin else None
    if data.enabled and not was:
        row.enabled_at = _now()
    record(
        db,
        PlatformAction.MAINTENANCE_ON if data.enabled else PlatformAction.MAINTENANCE_OFF,
        admin_id,
        details={"message": message, "was_on": was},
    )
    db.commit()
    db.refresh(row)
    switch.remember(row.enabled, row.message)
    return maintenance(db, switch)


# ------------------------------------------------------------------ platform settings


def platform_settings() -> PlatformSettingsOut:
    """How the platform is set up, from the environment. Never a secret, a key or a connection
    string: only switches, names and numbers."""
    s = get_settings()
    return PlatformSettingsOut(
        security=SecuritySettings(
            environment=s.app_env.value,
            base_domain=s.base_domain,
            admin_subdomain=s.admin_subdomain,
            default_company=s.default_tenant_slug or None,
            api_docs_enabled=s.enable_api_docs,
            cookie_secure=s.cookie_secure,
            insecure_cookies_allowed=s.allow_insecure_cookies,
            row_level_security_role_set=bool(s.db_app_role),
            jwt_algorithm=s.jwt_algorithm,
            access_token_minutes=s.access_token_minutes,
            refresh_token_hours=s.refresh_token_hours,
            login_max_attempts=s.login_max_attempts,
            login_lock_minutes=s.login_lock_minutes,
            cors_origins=list(s.cors_origins),
            storage_provider=s.storage_provider.value,
            gsp_provider=s.gsp_provider.value,
            backups_watched=bool(s.backup_dir),
            max_upload_mb=s.max_upload_mb,
        ),
        lifecycle=LifecycleSettings(
            trial_days=TRIAL_DAYS,
            max_trial_days=MAX_TRIAL_DAYS,
            banner_days=BANNER_DAYS,
            ending_soon_days=ENDING_SOON_DAYS,
            notice_days=rules.EXPIRING_DAYS,
            backup_stale_hours=rules.BACKUP_STALE_HOURS,
            disk_low_free_percent=rules.DISK_LOW_FREE_PERCENT,
            failed_admin_sign_ins_limit=rules.FAILED_ADMIN_SIGN_INS_LIMIT,
            maintenance_cache_seconds=rules.MAINTENANCE_CACHE_SECONDS,
        ),
    )
