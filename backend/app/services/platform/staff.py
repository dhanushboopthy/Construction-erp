"""Duolink's own staff, managed by a Super Admin (Milestone 17, ADR 0013).

A new member gets a temporary password and must change it before anything else. The rules about
who may lower whose access live in domain/platform_staff.py; here they are read and enforced
under a row lock, so two Super Admins demoting each other at once cannot leave none.
"""

import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.security import hash_password
from app.domain.platform_staff import (
    StaffMember,
    StaffRuleError,
    check_staff_change,
)
from app.models.enums import PlatformAction, PlatformRole
from app.models.platform import PlatformAdmin, PlatformSession
from app.schemas.platform import StaffCreate, StaffRow, StaffUpdate
from app.services.platform.audit import record
from app.services.platform.auth import revoke_all


def _now() -> datetime:
    return datetime.now(UTC)


def _row(db: Session, admin: PlatformAdmin) -> StaffRow:
    open_sessions = db.execute(
        select(func.count())
        .select_from(PlatformSession)
        .where(
            PlatformSession.admin_id == admin.id,
            PlatformSession.revoked_at.is_(None),
            PlatformSession.expires_at > _now(),
        )
    ).scalar_one()
    return StaffRow(
        id=admin.id,
        email=admin.email,
        full_name=admin.full_name,
        mobile=admin.mobile,
        role=admin.role,
        is_active=admin.is_active,
        locked=bool(admin.locked_until and admin.locked_until > _now()),
        must_change_password=admin.must_change_password,
        open_sessions=open_sessions,
        last_login_at=admin.last_login_at,
        created_at=admin.created_at,
    )


def list_staff(db: Session) -> list[StaffRow]:
    admins = db.execute(
        select(PlatformAdmin).order_by(PlatformAdmin.is_active.desc(), PlatformAdmin.full_name)
    ).scalars()
    return [_row(db, admin) for admin in admins]


def _member(db: Session, admin_id: int) -> PlatformAdmin:
    admin = db.get(PlatformAdmin, admin_id)
    if admin is None:
        raise NotFoundError("Staff member not found")
    return admin


def _lock_super_admins(db: Session) -> int:
    """Active Super Admins, counted under a lock so concurrent demotions are serialised."""
    ids = db.execute(
        select(PlatformAdmin.id)
        .where(PlatformAdmin.role == PlatformRole.SUPER_ADMIN, PlatformAdmin.is_active.is_(True))
        .with_for_update()
    ).all()
    return len(ids)


def create_staff(db: Session, body: StaffCreate, actor_id: int) -> StaffRow:
    email = body.email.strip().lower()
    if db.execute(select(PlatformAdmin.id).where(PlatformAdmin.email == email)).first():
        raise ConflictError(
            "A staff member with this email exists already", code="EMAIL_TAKEN", field="email"
        )
    admin = PlatformAdmin(
        email=email,
        full_name=body.full_name,
        mobile=body.mobile,
        password_hash=hash_password(body.password),
        role=body.role,
        must_change_password=True,  # the password was typed by someone else
        is_active=True,
        failed_login_count=0,
    )
    db.add(admin)
    db.flush()
    record(
        db,
        PlatformAction.STAFF_CREATE,
        actor_id,
        target_admin_id=admin.id,
        details={"email": email, "role": body.role.value},
    )
    db.commit()
    return _row(db, admin)


def update_staff(db: Session, admin_id: int, body: StaffUpdate, actor_id: int) -> StaffRow:
    admin = _member(db, admin_id)
    new_role = body.role if body.role is not None else admin.role
    new_active = body.is_active if body.is_active is not None else admin.is_active
    active_super_admins = _lock_super_admins(db)
    try:
        check_staff_change(
            actor_id,
            StaffMember(admin.id, admin.role.value, admin.is_active),
            new_role=new_role.value,
            new_active=new_active,
            active_super_admins=active_super_admins,
        )
    except StaffRuleError as exc:
        db.rollback()
        raise BusinessRuleError(str(exc), code=exc.code) from exc

    changes: dict[str, Any] = {}
    if body.full_name is not None and body.full_name != admin.full_name:
        changes["full_name"] = {"old": admin.full_name, "new": body.full_name}
        admin.full_name = body.full_name
    if "mobile" in body.model_fields_set and body.mobile != admin.mobile:
        changes["mobile"] = {"old": admin.mobile, "new": body.mobile}
        admin.mobile = body.mobile
    if new_role != admin.role:
        changes["role"] = {"old": admin.role.value, "new": new_role.value}
        admin.role = new_role
    if new_active != admin.is_active:
        changes["is_active"] = {"old": admin.is_active, "new": new_active}
        admin.is_active = new_active
        if not new_active:
            revoke_all(db, admin.id)  # a deactivated member is signed out at once
    if changes:
        details: dict[str, Any] = {"changes": changes}
        if body.reason:
            details["reason"] = body.reason
        record(db, PlatformAction.STAFF_UPDATE, actor_id, target_admin_id=admin.id, details=details)
    db.commit()
    return _row(db, admin)


def reset_password(db: Session, admin_id: int, actor_id: int) -> str:
    """A random temporary password, shown once. The member's sessions end and a lockout clears;
    they must change it at the next sign-in."""
    admin = _member(db, admin_id)
    password = secrets.token_urlsafe(12)
    admin.password_hash = hash_password(password)
    admin.must_change_password = True
    admin.locked_until = None
    admin.failed_login_count = 0
    revoke_all(db, admin.id)
    record(db, PlatformAction.STAFF_RESET_PASSWORD, actor_id, target_admin_id=admin.id)
    db.commit()
    return password


def unlock(db: Session, admin_id: int, actor_id: int) -> StaffRow:
    admin = _member(db, admin_id)
    admin.locked_until = None
    admin.failed_login_count = 0
    record(db, PlatformAction.STAFF_UNLOCK, actor_id, target_admin_id=admin.id)
    db.commit()
    return _row(db, admin)


def sign_out(db: Session, admin_id: int, actor_id: int) -> StaffRow:
    admin = _member(db, admin_id)
    revoke_all(db, admin.id)
    record(db, PlatformAction.STAFF_SIGN_OUT, actor_id, target_admin_id=admin.id)
    db.commit()
    return _row(db, admin)
