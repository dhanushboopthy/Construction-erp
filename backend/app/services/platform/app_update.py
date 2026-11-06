"""Force update (Milestone 29, ADR 0013): a Super Admin asks every open browser to look for a new
build now rather than at its next half-hourly check.

Forcing adds one to the release generation and does nothing else: no reload, no business data
touched. A browser that sees the new generation asks its service worker to check for an update,
exactly as it does every 30 minutes; if a new build is there, the "Update now" toast appears
and the person chooses when to take it, never in the middle of a bill.
"""

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.enums import PlatformAction
from app.models.platform import PlatformAdmin, PlatformAppUpdate
from app.schemas.app_update import AppUpdateOut
from app.services.platform.audit import record


def _row(db: Session) -> PlatformAppUpdate:
    row = db.get(PlatformAppUpdate, 1)
    if row is None:  # migration 0042 makes the row; this only guards a hand-built database
        row = PlatformAppUpdate(id=1, generation=0)
        db.add(row)
        db.flush()
    return row


def status(db: Session) -> AppUpdateOut:
    """The generation, when and by whom it was last forced, and the backend's build."""
    settings = get_settings()
    row = _row(db)
    forced_by = (
        db.execute(
            select(PlatformAdmin.full_name).where(PlatformAdmin.id == row.forced_by)
        ).scalar_one_or_none()
        if row.forced_by is not None
        else None
    )
    return AppUpdateOut(
        generation=row.generation,
        forced_at=row.forced_at,
        forced_by=forced_by,
        backend_version=settings.app_version,
        backend_build=settings.app_build or "dev",
    )


def force(db: Session, admin_id: int, reason: str | None) -> AppUpdateOut:
    """One more generation, in one statement so two admins forcing at once both count; audited
    with the new generation and the reason."""
    _row(db)
    now = datetime.now(UTC)
    generation = db.execute(
        update(PlatformAppUpdate)
        .where(PlatformAppUpdate.id == 1)
        .values(generation=PlatformAppUpdate.generation + 1, forced_at=now, forced_by=admin_id)
        .returning(PlatformAppUpdate.generation)
        .execution_options(synchronize_session=False)
    ).scalar_one()
    record(
        db,
        PlatformAction.APP_UPDATE_FORCE,
        admin_id,
        details={"generation": generation, "reason": (reason or "").strip() or None},
    )
    db.commit()
    db.expire_all()
    return status(db)
