"""The installable app and force update (Milestone 29, ADR 0013)."""

from fastapi import APIRouter

from app.api.deps import DbSession, PlatformAdminUser, SuperAdminOnly
from app.schemas.app_update import AppUpdateOut, ForceUpdateIn
from app.services.platform import app_update as service

router = APIRouter(prefix="/system", tags=["admin"])


@router.get("/app-update", response_model=AppUpdateOut)
def app_update_status(_: PlatformAdminUser, db: DbSession) -> AppUpdateOut:
    """The release generation every open browser compares with, when it was last forced and by
    whom, and the backend's version and build."""
    return service.status(db)


@router.post("/force-update", response_model=AppUpdateOut)
def force_update(body: ForceUpdateIn, admin: SuperAdminOnly, db: DbSession) -> AppUpdateOut:
    """Ask every open browser to look for a new build now (Super Admin). Adds one to the
    generation and nothing else: nobody is reloaded, and a new build waits for the person to
    press "Update now"."""
    return service.force(db, admin.admin_id, body.reason)
