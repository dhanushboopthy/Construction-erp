"""System health, notifications, maintenance mode and platform settings (Milestone 24).

Counts, statuses and configuration only: no amount, no secret, no connection string. Field names
avoid the words the admin money test looks for (`value`, `rate`, `paid` and the rest).
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.domain.platform_health import MAINTENANCE_MESSAGE_MAX, Level
from app.schemas.common import Schema
from app.schemas.system import Check


class MaintenanceNotice(Schema):
    """What a company's screen needs: is it closed, and Duolink's message."""

    enabled: bool
    message: str | None


class MaintenanceOut(Schema):
    enabled: bool
    message: str | None
    cause: Literal["operator", "restore"] | None
    # The persisted operator switch, as last saved.
    operator_enabled: bool
    operator_message: str | None
    changed_by: str | None
    enabled_at: datetime | None
    updated_at: datetime | None
    restoring: bool  # the in-memory restore flag (Milestone 25)


class MaintenanceIn(Schema):
    enabled: bool
    message: str | None = Field(default=None, max_length=MAINTENANCE_MESSAGE_MAX + 200)


class ApiHealth(Schema):
    started_at: datetime
    uptime_seconds: int
    version: str  # APP_VERSION, the build stamp
    changelog_version: str | None  # the newest release in CHANGELOG.md, when it is shipped
    python_version: str
    environment: str


class DatabaseHealth(Schema):
    up: bool
    round_trip_ms: Decimal
    size_bytes: int
    connections_in_use: int
    server_version: str
    migrations: Check


class DiskHealth(Schema):
    name: str  # "backups" or "files"
    watched: bool  # false when the folder is not configured or not reachable here
    total_bytes: int | None
    free_bytes: int | None
    free_percent: Decimal | None
    low: bool


class BackupHealth(Schema):
    check: Check
    last_success_at: datetime | None
    age_hours: int | None
    stale: bool
    offsite_synced_at: datetime | None  # when scripts/offsite-sync.sh last succeeded, if known


class HealthCounters(Schema):
    companies: int
    active_users: int
    open_sessions: int
    audit_events_today: int  # entries in the companies' audit logs since midnight (India)
    admin_actions_today: int  # entries in Duolink's own audit log since midnight (India)
    open_tickets: int


class SystemHealth(Schema):
    as_of: datetime
    api: ApiHealth
    database: DatabaseHealth
    disks: list[DiskHealth]
    backup: BackupHealth
    gsp: Check
    counters: HealthCounters
    maintenance: MaintenanceNotice


class NotificationOut(Schema):
    id: str
    level: Level
    title: str
    body: str
    link: str


class NotificationsOut(Schema):
    count: int
    items: list[NotificationOut]


class SecuritySettings(Schema):
    environment: str
    base_domain: str
    admin_subdomain: str
    default_company: str | None
    api_docs_enabled: bool
    cookie_secure: bool
    insecure_cookies_allowed: bool
    row_level_security_role_set: bool
    jwt_algorithm: str
    access_token_minutes: int
    refresh_token_hours: int
    login_max_attempts: int
    login_lock_minutes: int
    cors_origins: list[str]
    storage_provider: str
    gsp_provider: str
    backups_watched: bool
    max_upload_mb: int


class LifecycleSettings(Schema):
    trial_days: int
    max_trial_days: int
    banner_days: int  # the company sees "your plan ends in N days" from this many days before
    ending_soon_days: int
    notice_days: int  # the bell warns this many days before a subscription or trial ends
    backup_stale_hours: int
    disk_low_free_percent: int
    failed_admin_sign_ins_limit: int
    maintenance_cache_seconds: int


class PlatformSettingsOut(Schema):
    security: SecuritySettings
    lifecycle: LifecycleSettings
