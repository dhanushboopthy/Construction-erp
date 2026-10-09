"""Request dependencies: database session, the signed-in user (principal) and role checks.

Permissions are enforced here, in the API, not only in the screens (rule B4).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.security import decode_access_token
from app.models.enums import Role
from app.models.setup import AppUser
from app.services.audit import set_actor

_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


@dataclass(frozen=True)
class Principal:
    user_id: int
    tenant_id: int
    username: str
    role: Role
    location_ids: frozenset[int]
    session_id: str

    @property
    def is_owner(self) -> bool:
        return self.role is Role.OWNER

    @property
    def sees_cost(self) -> bool:
        """Cost, margin and profit are owner-only. Strip them from responses otherwise."""
        return self.role is Role.OWNER

    def can_access_location(self, location_id: int) -> bool:
        """Owners and accountants see every location; counter staff only their own shop."""
        return self.role is not Role.COUNTER or location_id in self.location_ids


def get_principal(
    request: Request,
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    if credentials is None:
        raise AuthenticationError("Sign in to continue")
    try:
        claims = decode_access_token(credentials.credentials)
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Your session has expired. Sign in again.") from exc

    user = db.get(AppUser, claims.user_id)
    if user is None or not user.is_active or user.tenant_id != claims.tenant_id:
        raise AuthenticationError("This account is not active")

    set_actor(db, user.id)
    request.state.user_id = user.id
    return Principal(
        user_id=user.id,
        tenant_id=user.tenant_id,
        username=user.username,
        role=user.role,  # read fresh from the database, not trusted from the token
        location_ids=frozenset(loc.id for loc in user.locations),
        session_id=claims.session_id,
    )


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def require_roles(*roles: Role) -> Callable[[Principal], Principal]:
    allowed = frozenset(roles)

    def checker(principal: CurrentPrincipal) -> Principal:
        if principal.role not in allowed:
            raise PermissionDeniedError("You do not have permission to do this")
        return principal

    return checker


OwnerOnly = Annotated[Principal, Depends(require_roles(Role.OWNER))]
OwnerOrAccountant = Annotated[Principal, Depends(require_roles(Role.OWNER, Role.ACCOUNTANT))]
