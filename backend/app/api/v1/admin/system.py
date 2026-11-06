"""System health, the notifications bell, maintenance mode and platform settings (Milestone 24).
Every admin reads these; only a Super Admin switches maintenance mode."""

from datetime import datetime

from fastapi import APIRouter, Request

from app.api.deps import DbSession, Maintenance, PlatformAdminUser, SuperAdminOnly
from app.schemas.platform_system import (
    MaintenanceIn,
    MaintenanceOut,
    NotificationsOut,
    PlatformSettingsOut,
    SystemHealth,
)
from app.services.platform import system as service

router = APIRouter(tags=["admin"])


@router.get("/system/health", response_model=SystemHealth)
def health(
    request: Request, _: PlatformAdminUser, db: DbSession, switch: Maintenance
) -> SystemHealth:
    """API uptime and version, database round trip, size and connections, free disk space,
    the last backup and off-site copy, and counters across every company. No secret and no
    connection string is ever in it."""
    started_at: datetime = request.app.state.started_at
    return service.health(db, started_at=started_at, switch=switch)


@router.get("/notifications", response_model=NotificationsOut)
def notifications(_: PlatformAdminUser, db: DbSession) -> NotificationsOut:
    """The bell: what needs attention, most serious first. Worked out on every read."""
    return service.notifications(db)


@router.get("/system/maintenance", response_model=MaintenanceOut)
def get_maintenance(_: PlatformAdminUser, db: DbSession, switch: Maintenance) -> MaintenanceOut:
    return service.maintenance(db, switch)


@router.post("/system/maintenance", response_model=MaintenanceOut)
def set_maintenance(
    body: MaintenanceIn, admin: SuperAdminOnly, db: DbSession, switch: Maintenance
) -> MaintenanceOut:
    """Close the platform to companies (`enabled: true`, with an optional message) or open it
    again (Super Admin). Kept across restarts until turned off. Audited. 409 MESSAGE_TOO_LONG."""
    return service.set_maintenance(db, switch, body, admin.admin_id)


@router.get("/system/settings", response_model=PlatformSettingsOut)
def platform_settings(_: PlatformAdminUser) -> PlatformSettingsOut:
    """How the platform is configured, from the environment (never a secret), and the numbers
    behind the subscription lifecycle."""
    return service.platform_settings()
