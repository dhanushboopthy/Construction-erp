"""User management (owner only)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.security import hash_password
from app.core.tenancy import TENANT_ID
from app.models.enums import AuditAction, Role
from app.models.setup import AppUser, Location
from app.schemas.user import UserCreate, UserUpdate
from app.services.audit import record_event
from app.services.auth import revoke_all


def list_users(db: Session) -> list[AppUser]:
    return list(
        db.execute(
            select(AppUser).where(AppUser.tenant_id == TENANT_ID).order_by(AppUser.username)
        ).scalars()
    )


def get_user(db: Session, user_id: int) -> AppUser:
    user = db.get(AppUser, user_id)
    if user is None or user.tenant_id != TENANT_ID:
        raise NotFoundError("User not found")
    return user


def _locations(db: Session, ids: list[int]) -> list[Location]:
    if not ids:
        return []
    found = list(
        db.execute(
            select(Location).where(Location.id.in_(ids), Location.tenant_id == TENANT_ID)
        ).scalars()
    )
    if len(found) != len(set(ids)):
        raise NotFoundError("One or more locations do not exist", field="location_ids")
    return found


def _check_counter_has_shop(role: Role, locations: list[Location]) -> None:
    if role is Role.COUNTER and not locations:
        raise BusinessRuleError(
            "Counter staff must be assigned to at least one shop",
            code="COUNTER_NEEDS_LOCATION",
            field="location_ids",
        )


def create_user(db: Session, data: UserCreate) -> AppUser:
    exists = db.execute(
        select(AppUser.id).where(AppUser.tenant_id == TENANT_ID, AppUser.username == data.username)
    ).first()
    if exists:
        raise ConflictError("That username is taken", code="USERNAME_TAKEN", field="username")
    locations = _locations(db, data.location_ids)
    _check_counter_has_shop(data.role, locations)
    user = AppUser(
        tenant_id=TENANT_ID,
        username=data.username,
        full_name=data.full_name,
        role=data.role,
        password_hash=hash_password(data.password),
        locations=locations,
    )
    db.add(user)
    db.commit()
    return user


def _active_owner_count(db: Session) -> int:
    return db.execute(
        select(func.count()).where(
            AppUser.tenant_id == TENANT_ID,
            AppUser.role == Role.OWNER,
            AppUser.is_active.is_(True),
        )
    ).scalar_one()


def update_user(db: Session, user_id: int, data: UserUpdate, acting_user_id: int) -> AppUser:
    user = get_user(db, user_id)
    removing_owner = user.role is Role.OWNER and (
        (data.role is not None and data.role is not Role.OWNER) or data.is_active is False
    )
    if removing_owner and _active_owner_count(db) <= 1:
        raise BusinessRuleError("There must always be at least one active owner", code="LAST_OWNER")
    if user_id == acting_user_id and data.is_active is False:
        raise BusinessRuleError("You cannot deactivate yourself", code="SELF_DEACTIVATION")

    if data.full_name is not None:
        user.full_name = data.full_name
    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active
        if not data.is_active:
            revoke_all(db, user.id)
    if data.location_ids is not None:
        before = sorted(loc.id for loc in user.locations)
        user.locations = _locations(db, data.location_ids)
        after = sorted(loc.id for loc in user.locations)
        if before != after:
            record_event(
                db,
                AuditAction.UPDATE,
                "app_user",
                user.id,
                {"location_ids": {"from": before, "to": after}},
            )
    _check_counter_has_shop(user.role, user.locations)
    db.commit()
    return user


def reset_password(db: Session, user_id: int, new_password: str) -> None:
    user = get_user(db, user_id)
    user.password_hash = hash_password(new_password)
    user.failed_login_count = 0
    user.locked_until = None
    revoke_all(db, user.id)
    db.commit()
