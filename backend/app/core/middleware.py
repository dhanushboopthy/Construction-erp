"""Request id, access log and basic security headers."""

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from app.core.context import client_ip_var, request_id_var

access_logger = logging.getLogger("app.access")

REQUEST_ID_HEADER = "X-Request-ID"
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
}
_QUIET_PATHS = {"/api/v1/health", "/api/v1/health/ready"}


def register_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if 0 < len(incoming) <= 64 else uuid.uuid4().hex
        rid_token = request_id_var.set(request_id)
        # Behind nginx, `uvicorn --proxy-headers` already resolves the real client address.
        ip_token = client_ip_var.set(request.client.host if request.client else None)
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            for key, value in _SECURITY_HEADERS.items():
                response.headers.setdefault(key, value)
            if request.url.path.startswith("/api/"):
                # Money, balances and cost figures must never sit in a shared browser cache.
                response.headers.setdefault("Cache-Control", "no-store")
            return response
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            if request.url.path not in _QUIET_PATHS:
                access_logger.info(
                    "%s %s %s %sms",
                    request.method,
                    request.url.path,
                    status_code,
                    duration_ms,
                    extra={
                        "status": status_code,
                        "duration_ms": duration_ms,
                        "user_id": getattr(request.state, "user_id", None),
                    },
                )
            request_id_var.reset(rid_token)
            client_ip_var.reset(ip_token)
