from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DbSession, Maintenance
from app.schemas.platform_system import MaintenanceNotice

router = APIRouter(prefix="/health", tags=["health"])
maintenance_router = APIRouter(prefix="/maintenance", tags=["health"])


@router.get("", summary="Liveness: the process is up")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/live", summary="Liveness: the process is up (same as /health)")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", summary="Readiness: the database answers")
def ready(db: DbSession) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}


@maintenance_router.get("", response_model=MaintenanceNotice)
def notice(db: DbSession, switch: Maintenance) -> MaintenanceNotice:
    """Is the platform closed for maintenance, and Duolink's message (Milestone 24). Open to
    anyone and never closed itself: the company's "Back soon" screen asks it every 30 seconds."""
    state = switch.state(db)
    return MaintenanceNotice(enabled=state.enabled, message=state.message)
