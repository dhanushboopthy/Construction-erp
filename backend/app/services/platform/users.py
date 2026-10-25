"""Users of every company, for Duolink support: find them, and deactivate, reactivate, unlock,
reset a password or end every session. Each action works on the user's own company and reuses
services/users.py, so the company's rules (one active owner at least, plan limits) still hold."""

import secrets
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.tenancy import set_tenant
from app.models.enums import PlatformAction, Role
from app.models.setup import AppUser
from app.models.tenancy import Tenant
from app.schemas.platform import PlatformUserRow
from app.schemas.user import UserUpdate
from app.services import users as user_service
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
    )


def list_users(
    db: Session,
    *,
    tenant_id: int | None = None,
    q: str | None = None,
    role: Role | None = None,
    state: str | None = None,  # active | inactive | locked
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[PlatformUserRow], int]:
    filters = []
    if tenant_id is not None:
        filters.append(AppUser.tenant_id == tenant_id)
    if q:
        like = f"%{q.strip()}%"
        filters.append(or_(AppUser.username.ilike(like), AppUser.full_name.ilike(like)))
    if role:
        filters.append(AppUser.role == role)
    if state == "active":
        filters.append(AppUser.is_active.is_(True))
    elif state == "inactive":
        filters.append(AppUser.is_active.is_(False))
    elif state == "locked":
        filters.append(AppUser.locked_until > _now())
    base = select(AppUser, Tenant).join(Tenant, Tenant.id == AppUser.tenant_id).where(*filters)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(
        base.order_by(Tenant.name, AppUser.username).limit(limit).offset(offset)
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


def set_active(db: Session, user_id: int, active: bool, admin_id: int) -> PlatformUserRow:
    user, tenant = _user(db, user_id)
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
    user.locked_until = None
    user.failed_login_count = 0
    record(db, PlatformAction.USER_UNLOCK, admin_id, tenant_id=tenant.id, target_user_id=user.id)
    db.commit()
    return _row(user, tenant)


def reset_password(db: Session, user_id: int, admin_id: int) -> str:
    """A random temporary password, shown once. The user's sessions end and a lockout clears."""
    user, tenant = _user(db, user_id)
    password = secrets.token_urlsafe(12)
    record(
        db,
        PlatformAction.USER_RESET_PASSWORD,
        admin_id,
        tenant_id=tenant.id,
        target_user_id=user.id,
    )
    user_service.reset_password(db, user.id, password)
    return password


def sign_out(db: Session, user_id: int, admin_id: int) -> PlatformUserRow:
    user, tenant = _user(db, user_id)
    revoke_all(db, user.id)
    record(db, PlatformAction.USER_SIGN_OUT, admin_id, tenant_id=tenant.id, target_user_id=user.id)
    db.commit()
    return _row(user, tenant)
