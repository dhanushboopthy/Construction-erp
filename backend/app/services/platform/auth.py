"""Duolink admin sign-in: the same rules as company users (services/auth.py) on separate tables.

Argon2 passwords, lockout after repeated failures, a 30-minute access token of type "platform",
and a refresh token kept hashed, rotated on use, whose reuse ends every session of the admin.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AccountLockedError, AuthenticationError
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    PlatformClaims,
    create_platform_token,
    hash_password,
    verify_password,
)
from app.models.enums import PlatformAction
from app.models.platform import PlatformAdmin, PlatformSession
from app.services.platform.audit import record


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    expires_in: int
    refresh_token: str
    refresh_expires_at: datetime
    admin: PlatformAdmin


def _now() -> datetime:
    return datetime.now(UTC)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _issue(
    db: Session, admin: PlatformAdmin, ip: str | None, user_agent: str | None
) -> tuple[IssuedTokens, PlatformSession]:
    settings = get_settings()
    refresh_token = secrets.token_urlsafe(48)
    session = PlatformSession(
        id=uuid.uuid4(),
        admin_id=admin.id,
        token_hash=_hash_token(refresh_token),
        expires_at=_now() + timedelta(hours=settings.refresh_token_hours),
        ip=ip,
        user_agent=(user_agent or "")[:255] or None,
    )
    db.add(session)
    access_token, expires_in = create_platform_token(PlatformClaims(admin.id, str(session.id)))
    return IssuedTokens(access_token, expires_in, refresh_token, session.expires_at, admin), session


def login(
    db: Session, email: str, password: str, ip: str | None, user_agent: str | None
) -> IssuedTokens:
    settings = get_settings()
    address = email.strip().lower()
    admin = db.execute(
        select(PlatformAdmin).where(PlatformAdmin.email == address)
    ).scalar_one_or_none()

    if admin is None:
        verify_password(password, DUMMY_PASSWORD_HASH)  # keep timing similar
        record(db, PlatformAction.LOGIN_FAILED, None, details={"email": address})
        db.commit()
        raise AuthenticationError("Wrong email or password")

    if admin.locked_until and admin.locked_until > _now():
        raise AccountLockedError("Too many wrong passwords. Try again later.")

    if not verify_password(password, admin.password_hash) or not admin.is_active:
        admin.failed_login_count += 1
        if admin.failed_login_count >= settings.login_max_attempts:
            admin.locked_until = _now() + timedelta(minutes=settings.login_lock_minutes)
            admin.failed_login_count = 0
        record(db, PlatformAction.LOGIN_FAILED, admin.id)
        db.commit()
        raise AuthenticationError("Wrong email or password")

    admin.failed_login_count = 0
    admin.locked_until = None
    admin.last_login_at = _now()
    tokens, _ = _issue(db, admin, ip, user_agent)
    record(db, PlatformAction.LOGIN, admin.id)
    db.commit()
    return tokens


def revoke_all(db: Session, admin_id: int) -> None:
    db.execute(
        update(PlatformSession)
        .where(PlatformSession.admin_id == admin_id, PlatformSession.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


def refresh(
    db: Session, refresh_token: str | None, ip: str | None, user_agent: str | None
) -> IssuedTokens:
    if not refresh_token:
        raise AuthenticationError("Sign in to continue")
    session = db.execute(
        select(PlatformSession).where(PlatformSession.token_hash == _hash_token(refresh_token))
    ).scalar_one_or_none()
    if session is None:
        raise AuthenticationError("Sign in to continue")

    if session.revoked_at is not None:
        # A rotated token was used again: likely stolen. End every session of this admin.
        revoke_all(db, session.admin_id)
        record(db, PlatformAction.TOKEN_REUSE, session.admin_id)
        db.commit()
        raise AuthenticationError("Your session ended. Sign in again.")

    admin = db.get(PlatformAdmin, session.admin_id)
    if session.expires_at <= _now() or admin is None or not admin.is_active:
        session.revoked_at = _now()
        db.commit()
        raise AuthenticationError("Your session has expired. Sign in again.")

    tokens, new_session = _issue(db, admin, ip, user_agent)
    session.revoked_at = _now()
    session.replaced_by = new_session.id
    db.commit()
    return tokens


def logout(db: Session, refresh_token: str | None) -> None:
    if not refresh_token:
        return
    session = db.execute(
        select(PlatformSession).where(PlatformSession.token_hash == _hash_token(refresh_token))
    ).scalar_one_or_none()
    if session and session.revoked_at is None:
        session.revoked_at = _now()
        record(db, PlatformAction.LOGOUT, session.admin_id)
        db.commit()


def change_password(db: Session, admin: PlatformAdmin, current: str, new: str) -> None:
    if not verify_password(current, admin.password_hash):
        raise AuthenticationError("Current password is wrong", field="current_password")
    admin.password_hash = hash_password(new)
    revoke_all(db, admin.id)
    db.commit()


def create_admin(db: Session, email: str, full_name: str, password: str) -> PlatformAdmin:
    """For the server-side command only: there is no sign-up."""
    admin = PlatformAdmin(
        email=email.strip().lower(),
        full_name=full_name.strip(),
        password_hash=hash_password(password),
        is_active=True,
        failed_login_count=0,
    )
    db.add(admin)
    db.commit()
    return admin
