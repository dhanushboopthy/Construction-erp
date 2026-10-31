from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.api.deps import DbSession, PlatformAdminUser, SuperAdminOnly
from app.models.enums import Role
from app.schemas.common import Page
from app.schemas.platform import PlatformUserRow, TemporaryPassword
from app.services.platform import users as service

router = APIRouter(prefix="/users", tags=["admin"])


@router.get("", response_model=Page[PlatformUserRow])
def list_users(
    _: PlatformAdminUser,
    db: DbSession,
    tenant_id: int | None = None,
    q: str | None = None,
    role: Role | None = None,
    state: Literal["active", "inactive", "locked"] | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[PlatformUserRow]:
    rows, total = service.list_users(
        db, tenant_id=tenant_id, q=q, role=role, state=state, limit=limit, offset=offset
    )
    return Page[PlatformUserRow](items=rows, total=total, limit=limit, offset=offset)


@router.post("/{user_id}/deactivate", response_model=PlatformUserRow)
def deactivate(user_id: int, admin: SuperAdminOnly, db: DbSession) -> PlatformUserRow:
    """The user is signed out everywhere. A company keeps at least one active owner."""
    return service.set_active(db, user_id, False, admin.admin_id)


@router.post("/{user_id}/activate", response_model=PlatformUserRow)
def activate(user_id: int, admin: SuperAdminOnly, db: DbSession) -> PlatformUserRow:
    """Counts against the company's plan (PLAN_USER_LIMIT)."""
    return service.set_active(db, user_id, True, admin.admin_id)


@router.post("/{user_id}/unlock", response_model=PlatformUserRow)
def unlock(user_id: int, admin: SuperAdminOnly, db: DbSession) -> PlatformUserRow:
    return service.unlock(db, user_id, admin.admin_id)


@router.post("/{user_id}/reset-password", response_model=TemporaryPassword)
def reset_password(user_id: int, admin: SuperAdminOnly, db: DbSession) -> TemporaryPassword:
    """A temporary password, shown once. The user's sessions end; they should change it."""
    return TemporaryPassword(temporary_password=service.reset_password(db, user_id, admin.admin_id))


@router.post("/{user_id}/sign-out", response_model=PlatformUserRow)
def sign_out(user_id: int, admin: SuperAdminOnly, db: DbSession) -> PlatformUserRow:
    return service.sign_out(db, user_id, admin.admin_id)
