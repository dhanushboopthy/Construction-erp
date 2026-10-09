"""Password hashing (argon2) and access-token handling (JWT)."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

_hasher = PasswordHash.recommended()

MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _hasher.verify(password, password_hash)


# Used to keep login timing similar whether or not the username exists.
DUMMY_PASSWORD_HASH = hash_password("timing-equaliser-not-a-real-password")


@dataclass(frozen=True)
class AccessClaims:
    user_id: int
    tenant_id: int
    role: str
    session_id: str


def create_access_token(claims: AccessClaims, now: datetime | None = None) -> tuple[str, int]:
    """Return (token, seconds until expiry)."""
    settings = get_settings()
    now = now or datetime.now(UTC)
    ttl = timedelta(minutes=settings.access_token_minutes)
    payload: dict[str, Any] = {
        "sub": str(claims.user_id),
        "tid": claims.tenant_id,
        "role": claims.role,
        "sid": claims.session_id,
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, int(ttl.total_seconds())


def decode_access_token(token: str) -> AccessClaims:
    """Raise jwt.InvalidTokenError if the token is invalid, expired or not an access token."""
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "iat", "sub", "typ"]},
    )
    if payload.get("typ") != "access":
        raise jwt.InvalidTokenError("not an access token")
    return AccessClaims(
        user_id=int(payload["sub"]),
        tenant_id=int(payload["tid"]),
        role=str(payload["role"]),
        session_id=str(payload["sid"]),
    )
