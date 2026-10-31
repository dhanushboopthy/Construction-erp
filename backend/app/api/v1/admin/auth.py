"""Duolink admin sign-in. Same flow as company users (api/v1/auth.py) with its own cookie, scoped
to /api/v1/admin/auth, so a company's refresh cookie and an admin's never meet."""

from datetime import datetime

from fastapi import APIRouter, Request, Response, status

from app.api.deps import DbSession, PlatformAdminAnyState
from app.core.config import get_settings
from app.core.errors import AuthenticationError
from app.models.platform import PlatformAdmin
from app.schemas.platform import (
    AdminChangePassword,
    AdminLoginRequest,
    AdminOut,
    AdminTokenResponse,
)
from app.services.platform import auth as auth_service

router = APIRouter(prefix="/auth", tags=["admin"])
COOKIE_NAME = "duolink_admin_refresh"
COOKIE_PATH = "/api/v1/admin/auth"


def _set_cookie(response: Response, token: str, expires_at: datetime) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        expires=expires_at,
        path=COOKIE_PATH,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="strict",
    )


def _clear_cookie(response: Response) -> None:
    response.delete_cookie(
        COOKIE_NAME,
        path=COOKIE_PATH,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="strict",
    )


def _client(request: Request) -> tuple[str | None, str | None]:
    return (request.client.host if request.client else None), request.headers.get("user-agent")


def _tokens(response: Response, tokens: auth_service.IssuedTokens) -> AdminTokenResponse:
    _set_cookie(response, tokens.refresh_token, tokens.refresh_expires_at)
    return AdminTokenResponse(
        access_token=tokens.access_token,
        expires_in=tokens.expires_in,
        admin=AdminOut.model_validate(tokens.admin),
    )


@router.post("/login", response_model=AdminTokenResponse)
def login(
    body: AdminLoginRequest, request: Request, response: Response, db: DbSession
) -> AdminTokenResponse:
    ip, agent = _client(request)
    return _tokens(response, auth_service.login(db, body.email, body.password, ip, agent))


@router.post("/refresh", response_model=AdminTokenResponse)
def refresh(request: Request, response: Response, db: DbSession) -> AdminTokenResponse:
    ip, agent = _client(request)
    tokens = auth_service.refresh(db, request.cookies.get(COOKIE_NAME), ip, agent)
    return _tokens(response, tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: DbSession) -> None:
    auth_service.logout(db, request.cookies.get(COOKIE_NAME))
    _clear_cookie(response)


def _admin(db: DbSession, admin_id: int) -> PlatformAdmin:
    admin = db.get(PlatformAdmin, admin_id)
    if admin is None:
        raise AuthenticationError("This account is not active")
    return admin


@router.get("/me", response_model=AdminOut)
def me(principal: PlatformAdminAnyState, db: DbSession) -> AdminOut:
    return AdminOut.model_validate(_admin(db, principal.admin_id))


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: AdminChangePassword, principal: PlatformAdminAnyState, response: Response, db: DbSession
) -> None:
    """Changing the password signs the admin out everywhere, including this browser."""
    admin = _admin(db, principal.admin_id)
    auth_service.change_password(db, admin, body.current_password, body.new_password)
    _clear_cookie(response)
