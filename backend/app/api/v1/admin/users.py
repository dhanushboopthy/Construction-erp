import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DbSession, PlatformAdminUser, SuperAdminOnly
from app.models.enums import Role
from app.schemas.common import Page
from app.schemas.platform import (
    PlatformUserRow,
    PlatformUserUpdate,
    RemoveUserRequest,
    TemporaryPassword,
    UserSessionRow,
)
from app.services.platform import users as service

router = APIRouter(prefix="/users", tags=["admin"])


@router.get("", response_model=Page[PlatformUserRow])
def list_users(
    _: PlatformAdminUser,
    db: DbSession,
    tenant_id: int | None = None,
    q: Annotated[str | None, Query(description="username, full name or company")] = None,
    role: Role | None = None,
    active: bool | None = None,
    locked: bool | None = None,
    never_signed_in: bool | None = None,
    include_removed: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[PlatformUserRow]:
    """Removed accounts are hidden unless `include_removed` is set."""
    rows, total = service.list_users(
        db,
        tenant_id=tenant_id,
        q=q,
        role=role,
        active=active,
        locked=locked,
        never_signed_in=never_signed_in,
        include_removed=include_removed,
        limit=limit,
        offset=offset,
    )
    return Page[PlatformUserRow](items=rows, total=total, limit=limit, offset=offset)


@router.patch("/{user_id}", response_model=PlatformUserRow)
def update_user(
    user_id: int, body: PlatformUserUpdate, admin: SuperAdminOnly, db: DbSession
) -> PlatformUserRow:
    """Name, mobile, username (409 USERNAME_TAKEN) and role (409 LAST_OWNER,
    COUNTER_NEEDS_LOCATION). A reason is required."""
    return service.update(db, user_id, body, admin.admin_id)


@router.post("/{user_id}/deactivate", response_model=PlatformUserRow)
def deactivate(user_id: int, admin: SuperAdminOnly, db: DbSession) -> PlatformUserRow:
    """The user is signed out everywhere. A company keeps at least one active owner."""
    return service.set_active(db, user_id, False, admin.admin_id)


@router.post("/{user_id}/activate", response_model=PlatformUserRow)
def activate(user_id: int, admin: SuperAdminOnly, db: DbSession) -> PlatformUserRow:
    """Counts against the company's plan (PLAN_USER_LIMIT). A removed account stays removed."""
    return service.set_active(db, user_id, True, admin.admin_id)


@router.post("/{user_id}/unlock", response_model=PlatformUserRow)
def unlock(user_id: int, admin: SuperAdminOnly, db: DbSession) -> PlatformUserRow:
    return service.unlock(db, user_id, admin.admin_id)


@router.post("/{user_id}/reset-password", response_model=TemporaryPassword)
def reset_password(user_id: int, admin: SuperAdminOnly, db: DbSession) -> TemporaryPassword:
    """A temporary password, shown once. Every session of the user ends and the user must
    choose their own password before anything else (403 PASSWORD_CHANGE_REQUIRED)."""
    return TemporaryPassword(temporary_password=service.reset_password(db, user_id, admin.admin_id))


@router.post("/{user_id}/sign-out", response_model=PlatformUserRow)
def sign_out(user_id: int, admin: SuperAdminOnly, db: DbSession) -> PlatformUserRow:
    return service.sign_out(db, user_id, admin.admin_id)


@router.get("/{user_id}/sessions", response_model=list[UserSessionRow])
def list_sessions(user_id: int, _: PlatformAdminUser, db: DbSession) -> list[UserSessionRow]:
    """Where the user is signed in: device, address, first sign-in and last use."""
    return service.list_sessions(db, user_id)


@router.delete("/{user_id}/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(
    user_id: int, session_id: uuid.UUID, admin: SuperAdminOnly, db: DbSession
) -> Response:
    """End one session. Its access token runs out within minutes."""
    service.revoke_session(db, user_id, session_id, admin.admin_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{user_id}/remove", response_model=PlatformUserRow)
def remove_user(
    user_id: int, body: RemoveUserRequest, admin: SuperAdminOnly, db: DbSession
) -> PlatformUserRow:
    """Remove access: the account is deactivated, signed out and hidden, never deleted, so old
    documents keep the name. `confirm_username` must match exactly (409 CONFIRMATION_MISMATCH);
    the last active owner cannot be removed (409 LAST_OWNER)."""
    return service.remove(db, user_id, body, admin.admin_id)
