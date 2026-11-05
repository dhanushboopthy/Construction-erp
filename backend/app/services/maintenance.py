"""Maintenance mode as the companies meet it (Milestone 24, ADR 0013).

While it is on, every company request answers 503 MAINTENANCE with Duolink's message. The admin
API, the health checks, `GET /maintenance` and the company's name (`GET /tenant`, which the
"Back soon" screen and the sign-in page show) keep answering.

Each API process keeps one `MaintenanceSwitch` on `app.state`. It reads the persisted row at
most every 5 seconds, so a switch made through another process is seen within 5 seconds and a
switch made through this one at once. A rebuilt app (a restart) starts empty and reads the row
again, so maintenance survives a restart. The restore flag (M25) lives only in memory and is
forgotten by a restart, on purpose.
"""

import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import MaintenanceError, TenantRestoringError
from app.domain.backups import STALE_JOB_AFTER
from app.domain.platform_health import MaintenanceState, cache_is_fresh, effective_maintenance
from app.models.enums import BackupJobKind, BackupJobStatus
from app.models.platform import PlatformBackupJob, PlatformMaintenance

DEFAULT_MESSAGE = "Duolink is updating the ERP. Please try again in a few minutes."

# Company routes that stay open: the company's name and logo, for the "Back soon" screen.
OPEN_DURING_MAINTENANCE: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("GET", re.compile(r"^/api/v1/tenant$")),
    ("GET", re.compile(r"^/api/v1/tenant/logo$")),
)


@dataclass(frozen=True)
class _Persisted:
    enabled: bool
    message: str | None


def read_row(db: Session) -> PlatformMaintenance:
    """The singleton row; the migration inserts it, so it is always there."""
    row = db.get(PlatformMaintenance, 1)
    if row is None:  # a database built without migration 0037's insert
        row = PlatformMaintenance(id=1, enabled=False)
        db.add(row)
        db.flush()
    return row


class MaintenanceSwitch:
    def __init__(self) -> None:
        self._persisted = _Persisted(False, None)
        self._loaded_at: float | None = None
        self._restoring = False
        # One company's restore (Milestone 25): companies being restored by this process, and
        # the ones other processes are restoring, read from the running restore jobs.
        self._restoring_tenants: set[int] = set()
        self._remote_tenants: frozenset[int] = frozenset()
        self._remote_loaded_at: float | None = None

    def tenant_restoring(self, db: Session, tenant_id: int) -> bool:
        if tenant_id in self._restoring_tenants:
            return True
        now = time.monotonic()
        if not cache_is_fresh(self._remote_loaded_at, now):
            since = datetime.now(UTC) - STALE_JOB_AFTER
            rows = db.scalars(
                select(PlatformBackupJob.company_id).where(
                    PlatformBackupJob.kind == BackupJobKind.RESTORE_COMPANY,
                    PlatformBackupJob.status == BackupJobStatus.RUNNING,
                    PlatformBackupJob.started_at > since,
                    PlatformBackupJob.company_id.is_not(None),
                )
            )
            self._remote_tenants = frozenset(i for i in rows if i is not None)
            self._remote_loaded_at = now
        return tenant_id in self._remote_tenants

    def begin_tenant_restore(self, tenant_id: int) -> None:
        self._restoring_tenants.add(tenant_id)

    def end_tenant_restore(self, tenant_id: int) -> None:
        self._restoring_tenants.discard(tenant_id)
        self._remote_loaded_at = None

    def state(self, db: Session) -> MaintenanceState:
        now = time.monotonic()
        if not cache_is_fresh(self._loaded_at, now):
            row = db.get(PlatformMaintenance, 1)
            self._persisted = _Persisted(bool(row and row.enabled), row.message if row else None)
            self._loaded_at = now
        return effective_maintenance(
            operator_on=self._persisted.enabled,
            operator_message=self._persisted.message,
            restoring=self._restoring,
        )

    def remember(self, enabled: bool, message: str | None) -> None:
        """This process changed the row: take the new value now, not in 5 seconds."""
        self._persisted = _Persisted(enabled, message)
        self._loaded_at = time.monotonic()

    def forget(self) -> None:
        """Read the row again on the next request (tests; a fresh process starts like this)."""
        self._loaded_at = None
        self._remote_loaded_at = None

    @property
    def restoring(self) -> bool:
        return self._restoring

    def set_restoring(self, on: bool) -> None:
        """The in-memory switch a restore uses (Milestone 25). Never persisted."""
        self._restoring = on


def is_open(method: str, path: str) -> bool:
    return any(method == m and pattern.match(path) for m, pattern in OPEN_DURING_MAINTENANCE)


RESTORING_MESSAGE = "This company is being restored from a backup. It will be back shortly."


def enforce_tenant(
    switch: MaintenanceSwitch, db: Session, tenant_id: int, method: str, path: str
) -> None:
    """403 TENANT_RESTORING while this company's data is being replaced (Milestone 25). Other
    companies are not affected."""
    if is_open(method, path):
        return
    if switch.tenant_restoring(db, tenant_id):
        raise TenantRestoringError(RESTORING_MESSAGE, extra={"retry_after_seconds": 30})


def enforce(switch: MaintenanceSwitch, db: Session, method: str, path: str) -> None:
    """503 MAINTENANCE for a company request while either switch is on."""
    if is_open(method, path):
        return
    state = switch.state(db)
    if state.enabled:
        raise MaintenanceError(
            state.message or DEFAULT_MESSAGE,
            extra={"maintenance_message": state.message, "retry_after_seconds": 30},
        )
