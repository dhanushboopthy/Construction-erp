"""Sign-in, refresh-token rotation, sign-out and password changes."""

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
    AccessClaims,
    create_access_token,
    hash_password,
    verify_password,
)
from app.core.tenancy import TENANT_ID
from app.models.auth import AuthSession
from app.models.enums import AuditAction
from app.models.setup import AppUser
from app.services.audit import record_event, set_actor


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    expires_in: int
    refresh_token: str
    refresh_expires_at: datetime
    user: AppUser


def _now() -> datetime:
    return datetime.now(UTC)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _issue(
    db: Session, user: AppUser, ip: str | None, user_agent: str | None
) -> tuple[IssuedTokens, AuthSession]:
    settings = get_settings()
    refresh_token = secrets.token_urlsafe(48)
    session = AuthSession(
        id=uuid.uuid4(),
        tenant_id=user.tenant_id,
        user_id=user.id,
        token_hash=_hash_token(refresh_token),
        expires_at=_now() + timedelta(hours=settings.refresh_token_hours),
        ip=ip,
        user_agent=(user_agent or "")[:255] or None,
    )
    db.add(session)
    access_token, expires_in = create_access_token(
        AccessClaims(user.id, user.tenant_id, user.role.value, str(session.id))
    )
    tokens = IssuedTokens(access_token, expires_in, refresh_token, session.expires_at, user)
    return tokens, session


def login(
    db: Session, username: str, password: str, ip: str | None, user_agent: str | None
) -> IssuedTokens:
    settings = get_settings()
    user = db.execute(
        select(AppUser).where(
            AppUser.tenant_id == TENANT_ID, AppUser.username == username.strip().lower()
        )
    ).scalar_one_or_none()

    if user is None:
        verify_password(password, DUMMY_PASSWORD_HASH)  # keep timing similar
        record_event(db, AuditAction.LOGIN_FAILED, "app_user", None, {"username": username})
        db.commit()
        raise AuthenticationError("Wrong username or password")

    if user.locked_until and user.locked_until > _now():
        raise AccountLockedError("Too many wrong passwords. Try again later or ask the owner.")

    if not verify_password(password, user.password_hash) or not user.is_active:
        user.failed_login_count += 1
        if user.failed_login_count >= settings.login_max_attempts:
            user.locked_until = _now() + timedelta(minutes=settings.login_lock_minutes)
            user.failed_login_count = 0
        record_event(db, AuditAction.LOGIN_FAILED, "app_user", user.id, user_id=user.id)
        db.commit()
        raise AuthenticationError("Wrong username or password")

    set_actor(db, user.id)
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = _now()
    tokens, _ = _issue(db, user, ip, user_agent)
    record_event(db, AuditAction.LOGIN, "app_user", user.id)
    db.commit()
    return tokens


def refresh(
    db: Session, refresh_token: str | None, ip: str | None, user_agent: str | None
) -> IssuedTokens:
    if not refresh_token:
        raise AuthenticationError("Sign in to continue")
    session = db.execute(
        select(AuthSession).where(AuthSession.token_hash == _hash_token(refresh_token))
    ).scalar_one_or_none()
    if session is None:
        raise AuthenticationError("Sign in to continue")

    if session.revoked_at is not None:
        # A rotated token was used again: likely stolen. End every session of this user.
        revoke_all(db, session.user_id)
        record_event(
            db, AuditAction.TOKEN_REUSE, "auth_session", str(session.id), user_id=session.user_id
        )
        db.commit()
        raise AuthenticationError("Your session ended. Sign in again.")

    user = db.get(AppUser, session.user_id)
    if session.expires_at <= _now() or user is None or not user.is_active:
        session.revoked_at = _now()
        db.commit()
        raise AuthenticationError("Your session has expired. Sign in again.")

    tokens, new_session = _issue(db, user, ip, user_agent)
    session.revoked_at = _now()
    session.replaced_by = new_session.id
    db.commit()
    return tokens


def logout(db: Session, refresh_token: str | None) -> None:
    if not refresh_token:
        return
    session = db.execute(
        select(AuthSession).where(AuthSession.token_hash == _hash_token(refresh_token))
    ).scalar_one_or_none()
    if session and session.revoked_at is None:
        session.revoked_at = _now()
        record_event(db, AuditAction.LOGOUT, "app_user", session.user_id, user_id=session.user_id)
        db.commit()


def revoke_all(db: Session, user_id: int) -> None:
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


def change_password(db: Session, user: AppUser, current: str, new: str) -> None:
    if not verify_password(current, user.password_hash):
        raise AuthenticationError("Current password is wrong", field="current_password")
    user.password_hash = hash_password(new)
    revoke_all(db, user.id)
    db.commit()
