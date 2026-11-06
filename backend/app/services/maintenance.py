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

from sqlalchemy.orm import Session

from app.core.errors import MaintenanceError
from app.domain.platform_health import MaintenanceState, cache_is_fresh, effective_maintenance
from app.models.platform import PlatformMaintenance

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

    @property
    def restoring(self) -> bool:
        return self._restoring

    def set_restoring(self, on: bool) -> None:
        """The in-memory switch a restore uses (Milestone 25). Never persisted."""
        self._restoring = on


def is_open(method: str, path: str) -> bool:
    return any(method == m and pattern.match(path) for m, pattern in OPEN_DURING_MAINTENANCE)


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
