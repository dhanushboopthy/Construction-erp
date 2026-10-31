"""Users of every company, for Duolink support: find them, edit them, and deactivate, reactivate,
unlock, reset a password, end sessions or remove the account. Each action works on the user's own
company and reuses services/users.py, so the company's rules (one active owner at least, plan
limits) still hold. Every action is written to the platform audit log and, as "Duolink: <admin>",
to the company's own audit log."""

import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.tenancy import set_tenant
from app.domain import user_support
from app.models.auth import AuthSession
from app.models.enums import AuditAction, PlatformAction, Role
from app.models.setup import AppUser
from app.models.tenancy import Tenant
from app.schemas.platform import (
    PlatformUserRow,
    PlatformUserUpdate,
    RemoveUserRequest,
    UserSessionRow,
)
from app.schemas.user import UserUpdate
from app.services import users as user_service
from app.services.audit import record_event
from app.services.auth import revoke_all
from app.services.platform.audit import record

# A Duolink admin is never one of the company's users: no self-deactivation check applies.
NO_COMPANY_USER = 0


def _now() -> datetime:
    return datetime.now(UTC)


def _row(user: AppUser, tenant: Tenant) -> PlatformUserRow:
    return PlatformUserRow(
        id=user.id,
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        tenant_name=tenant.name,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        locked=bool(user.locked_until and user.locked_until > _now()),
        failed_login_count=user.failed_login_count,
        last_login_at=user.last_login_at,
        mobile=user.mobile,
        must_change_password=user.must_change_password,
        removed_at=user.removed_at,
    )


def list_users(
    db: Session,
    *,
    tenant_id: int | None = None,
    q: str | None = None,
    role: Role | None = None,
    active: bool | None = None,
    locked: bool | None = None,
    never_signed_in: bool | None = None,
    include_removed: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[PlatformUserRow], int]:
    now = _now()
    is_locked = AppUser.locked_until > now
    filters = []
    if tenant_id is not None:
        filters.append(AppUser.tenant_id == tenant_id)
    if q and q.strip():
        like = f"%{q.strip()}%"
        filters.append(
            or_(
                AppUser.username.ilike(like),
                AppUser.full_name.ilike(like),
                Tenant.name.ilike(like),
                Tenant.slug.ilike(like),
            )
        )
    if role:
        filters.append(AppUser.role == role)
    if active is not None:
        filters.append(AppUser.is_active.is_(active))
    if locked is True:
        filters.append(is_locked)
    elif locked is False:
        filters.append(or_(AppUser.locked_until.is_(None), AppUser.locked_until <= now))
    if never_signed_in is True:
        filters.append(AppUser.last_login_at.is_(None))
    elif never_signed_in is False:
        filters.append(AppUser.last_login_at.is_not(None))
    if not include_removed:
        filters.append(AppUser.removed_at.is_(None))
    base = select(AppUser, Tenant).join(Tenant, Tenant.id == AppUser.tenant_id).where(*filters)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(
        base.order_by(Tenant.name, AppUser.username, AppUser.id).limit(limit).offset(offset)
    ).all()
    return [_row(user, tenant) for user, tenant in rows], total


def _user(db: Session, user_id: int) -> tuple[AppUser, Tenant]:
    """The user, with the session switched to their company."""
    user = db.get(AppUser, user_id)
    if user is None:
        raise NotFoundError("User not found")
    tenant = db.get(Tenant, user.tenant_id)
    if tenant is None:
        raise NotFoundError("User not found")
    set_tenant(db, tenant.id)
    return user, tenant


def _company_event(db: Session, user: AppUser, what: str, **details: Any) -> None:
    """A line in the company's own audit log for something that changes no audited column.
    `_actor` ("Duolink: <admin>") is added by the session."""
    record_event(db, AuditAction.UPDATE, "app_user", user.id, {"support_action": what, **details})


def set_active(db: Session, user_id: int, active: bool, admin_id: int) -> PlatformUserRow:
    user, tenant = _user(db, user_id)
    user_service.refuse_if_removed(user)
    # update_user commits; the audit row is added first so it is saved in the same transaction.
    action = PlatformAction.USER_ACTIVATE if active else PlatformAction.USER_DEACTIVATE
    record(db, action, admin_id, tenant_id=tenant.id, target_user_id=user.id)
    try:
        user_service.update_user(db, user.id, UserUpdate(is_active=active), NO_COMPANY_USER)
    except Exception:
        db.rollback()
        raise
    return _row(user, tenant)


def unlock(db: Session, user_id: int, admin_id: int) -> PlatformUserRow:
    user, tenant = _user(db, user_id)
    user_service.refuse_if_removed(user)
    user.locked_until = None
    user.failed_login_count = 0
    record(db, PlatformAction.USER_UNLOCK, admin_id, tenant_id=tenant.id, target_user_id=user.id)
    _company_event(db, user, "unlock")
    db.commit()
    return _row(user, tenant)


def reset_password(db: Session, user_id: int, admin_id: int) -> str:
    """A random temporary password, shown once. The user's sessions end, a lockout clears and
    the user must choose their own password at the next sign-in."""
    user, tenant = _user(db, user_id)
    password = secrets.token_urlsafe(12)
    record(
        db,
        PlatformAction.USER_RESET_PASSWORD,
        admin_id,
        tenant_id=tenant.id,
        target_user_id=user.id,
    )
    _company_event(db, user, "reset_password")
    try:
        user_service.reset_password(db, user.id, password, must_change=True)
    except Exception:
        db.rollback()
        raise
    return password


def sign_out(db: Session, user_id: int, admin_id: int) -> PlatformUserRow:
    user, tenant = _user(db, user_id)
    revoke_all(db, user.id)
    record(db, PlatformAction.USER_SIGN_OUT, admin_id, tenant_id=tenant.id, target_user_id=user.id)
    _company_event(db, user, "sign_out")
    db.commit()
    return _row(user, tenant)


def update(db: Session, user_id: int, body: PlatformUserUpdate, admin_id: int) -> PlatformUserRow:
    """Name, mobile, username and role. The role goes through services/users.py, so "at least
    one active owner", the counter's shop and the plan limits still hold."""
    user, tenant = _user(db, user_id)
    user_service.refuse_if_removed(user)
    sent = body.model_fields_set
    changes: dict[str, dict[str, Any]] = {}

    def note(field: str, before: Any, after: Any) -> None:
        if before != after:
            changes[field] = {"from": before, "to": after}

    if "full_name" in sent and body.full_name is not None:
        note("full_name", user.full_name, body.full_name)
    if "mobile" in sent:
        note("mobile", user.mobile, body.mobile)
    if "username" in sent and body.username is not None:
        note("username", user.username, body.username)
    if "role" in sent and body.role is not None:
        note("role", user.role.value, body.role.value)
    if not changes:
        return _row(user, tenant)

    if "username" in changes:
        taken = db.execute(
            select(AppUser.id).where(
                AppUser.tenant_id == tenant.id,
                AppUser.username == body.username,
                AppUser.id != user.id,
            )
        ).first()
        if taken:
            raise ConflictError("That username is taken", code="USERNAME_TAKEN", field="username")
        user.username = changes["username"]["to"]
    if "mobile" in changes:
        user.mobile = body.mobile

    record(
        db,
        PlatformAction.USER_UPDATE,
        admin_id,
        tenant_id=tenant.id,
        target_user_id=user.id,
        details={"changes": changes, "reason": body.reason},
    )
    try:
        user_service.update_user(
            db,
            user.id,
            UserUpdate(
                full_name=changes.get("full_name", {}).get("to"),
                role=body.role if "role" in changes else None,
            ),
            NO_COMPANY_USER,
        )
    except Exception:
        db.rollback()
        raise
    return _row(user, tenant)


def remove(db: Session, user_id: int, body: RemoveUserRequest, admin_id: int) -> PlatformUserRow:
    """Take the account away. The row stays, because every document names its maker: the user
    is deactivated, signed out everywhere, marked removed and hidden from the company's list."""
    user, tenant = _user(db, user_id)
    user_service.refuse_if_removed(user)
    if not user_support.confirmation_matches(body.confirm_username, user.username):
        raise BusinessRuleError(
            "Type the username exactly to remove this account",
            code="CONFIRMATION_MISMATCH",
            field="confirm_username",
        )
    try:
        user_support.check_removal(
            is_owner=user.role is Role.OWNER,
            is_active=user.is_active,
            active_owners=user_service.active_owner_count(db),
        )
    except user_support.UserRuleError as err:
        raise BusinessRuleError(str(err), code=err.code) from err

    user.is_active = False
    user.removed_at = _now()
    revoke_all(db, user.id)
    record(
        db,
        PlatformAction.USER_REMOVE,
        admin_id,
        tenant_id=tenant.id,
        target_user_id=user.id,
        details={"username": user.username, "reason": body.reason},
    )
    _company_event(db, user, "remove", reason=body.reason)
    db.commit()
    return _row(user, tenant)


def _session_row(session: AuthSession) -> UserSessionRow:
    return UserSessionRow(
        id=session.id,
        device=user_support.device_label(session.user_agent),
        user_agent=session.user_agent,
        ip=session.ip,
        signed_in_at=session.signed_in_at or session.created_at,
        last_used_at=session.created_at,  # a refresh makes a new row, so this is the last use
        expires_at=session.expires_at,
    )


def list_sessions(db: Session, user_id: int) -> list[UserSessionRow]:
    """The places the user is signed in: one live session per device, newest first."""
    user, _ = _user(db, user_id)
    now = _now()
    rows = db.execute(
        select(AuthSession)
        .where(
            AuthSession.user_id == user.id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
        .order_by(AuthSession.created_at.desc())
    ).scalars()
    return [_session_row(s) for s in rows]


def revoke_session(db: Session, user_id: int, session_id: uuid.UUID, admin_id: int) -> None:
    user, tenant = _user(db, user_id)
    session = db.get(AuthSession, session_id)
    if (
        session is None
        or session.user_id != user.id
        or not user_support.session_is_live(session.revoked_at, session.expires_at, _now())
    ):
        raise NotFoundError("Session not found")
    session.revoked_at = _now()
    record(
        db,
        PlatformAction.USER_SESSION_REVOKE,
        admin_id,
        tenant_id=tenant.id,
        target_user_id=user.id,
        details={
            "session_id": str(session.id),
            "device": user_support.device_label(session.user_agent),
        },
    )
    _company_event(db, user, "revoke_session", session_id=str(session.id))
    db.commit()
