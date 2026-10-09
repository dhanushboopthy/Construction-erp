"""Sign-in flow.

The access token (30 min) is returned in the body and kept in memory by the web app. The
refresh token lives in an httpOnly, SameSite=Strict cookie scoped to /api/v1/auth, and is
rotated on every use.
"""

from datetime import datetime

from fastapi import APIRouter, Request, Response, status

from app.api.deps import CurrentPrincipal, DbSession
from app.core.config import get_settings
from app.schemas.auth import ChangePasswordRequest, LoginRequest, TokenResponse
from app.schemas.user import UserOut
from app.services import auth as auth_service
from app.services.users import get_user

router = APIRouter(prefix="/auth", tags=["auth"])
COOKIE_PATH = "/api/v1/auth"


def _set_refresh_cookie(response: Response, token: str, expires_at: datetime) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        expires=expires_at,
        path=COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


def _clear_refresh_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        settings.refresh_cookie_name,
        path=COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


def _client(request: Request) -> tuple[str | None, str | None]:
    return (request.client.host if request.client else None), request.headers.get("user-agent")


def _token_response(response: Response, tokens: auth_service.IssuedTokens) -> TokenResponse:
    _set_refresh_cookie(response, tokens.refresh_token, tokens.refresh_expires_at)
    return TokenResponse(
        access_token=tokens.access_token,
        expires_in=tokens.expires_in,
        user=UserOut.model_validate(tokens.user),
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, response: Response, db: DbSession) -> TokenResponse:
    ip, agent = _client(request)
    tokens = auth_service.login(db, body.username, body.password, ip, agent)
    return _token_response(response, tokens)


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: Request, response: Response, db: DbSession) -> TokenResponse:
    ip, agent = _client(request)
    token = request.cookies.get(get_settings().refresh_cookie_name)
    tokens = auth_service.refresh(db, token, ip, agent)
    return _token_response(response, tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: DbSession) -> None:
    auth_service.logout(db, request.cookies.get(get_settings().refresh_cookie_name))
    _clear_refresh_cookie(response)


@router.get("/me", response_model=UserOut)
def me(principal: CurrentPrincipal, db: DbSession) -> UserOut:
    return UserOut.model_validate(get_user(db, principal.user_id))


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: ChangePasswordRequest, principal: CurrentPrincipal, response: Response, db: DbSession
) -> None:
    """Changing the password signs the user out everywhere, including this browser."""
    user = get_user(db, principal.user_id)
    auth_service.change_password(db, user, body.current_password, body.new_password)
    _clear_refresh_cookie(response)
