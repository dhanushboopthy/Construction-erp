"""Error types and the JSON error contract: {code, message, field, request_id}.

Business-rule blocks (credit limit, below cost, return window) raise BusinessRuleError and
answer 409, so the counter screen can turn them into an owner-approval prompt.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.context import request_id_var

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "BAD_REQUEST"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        field: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.field = field
        self.extra = extra or {}
        if code:
            self.code = code


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"


class AuthenticationError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "NOT_AUTHENTICATED"


class PermissionDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "PERMISSION_DENIED"


class AccountLockedError(AppError):
    status_code = status.HTTP_423_LOCKED
    code = "ACCOUNT_LOCKED"


class BusinessRuleError(AppError):
    """A rule from docs/SPEC.md blocked the action. `requires_owner_approval` lets the UI
    offer an owner override instead of a dead end."""

    status_code = status.HTTP_409_CONFLICT
    code = "BUSINESS_RULE"

    def __init__(
        self,
        message: str,
        *,
        code: str,
        requires_owner_approval: bool = False,
        field: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, field=field, extra=extra)
        self.extra["requires_owner_approval"] = requires_owner_approval


def _body(code: str, message: str, field: str | None = None, **extra: Any) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "field": field,
        "request_id": request_id_var.get(),
        **extra,
    }


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(exc.code, exc.message, exc.field, **exc.extra),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        first = errors[0] if errors else {}
        loc = [str(p) for p in first.get("loc", []) if p not in ("body", "query", "path")]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=_body(
                "VALIDATION_ERROR",
                str(first.get("msg", "Invalid request")),
                ".".join(loc) or None,
                errors=[
                    {"field": ".".join(str(p) for p in e.get("loc", [])), "message": e.get("msg")}
                    for e in errors
                ],
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(code, str(exc.detail)),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error", exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_body("INTERNAL_ERROR", "Something went wrong. Quote the request id."),
        )
