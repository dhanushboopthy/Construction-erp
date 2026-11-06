"""FastAPI application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app import services as _services  # noqa: F401 - registers audit listeners
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import register_middleware
from app.schemas.common import ErrorResponse
from app.services.maintenance import MaintenanceSwitch
from app.services.platform.backups import thread_launcher
from app.services.platform.integrations import refuse_to_start_without_key

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Refuse to start when provider keys are saved but INTEGRATION_SECRET_KEY is missing
    (Milestone 27). A database that cannot be reached yet is not this check's business."""
    from app.core.db import SessionLocal

    try:
        with SessionLocal() as db:
            refuse_to_start_without_key(db)
    except SQLAlchemyError:
        logger.warning("Skipped the integration key check: the database is not ready")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)

    docs = settings.enable_api_docs
    application = FastAPI(
        lifespan=lifespan,
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/api/docs" if docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs else None,
        responses={
            400: {"model": ErrorResponse},
            401: {"model": ErrorResponse},
            403: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
        },
    )
    if settings.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID"],
        )
    register_middleware(application)
    register_error_handlers(application)
    application.include_router(api_router)
    # Milestone 24: uptime is counted from here, and the maintenance switch starts unread, so a
    # restarted process reads the persisted row on its first company request.
    application.state.started_at = datetime.now(UTC)
    application.state.maintenance = MaintenanceSwitch()
    # Milestone 25: backups and restores run as jobs on a thread of their own.
    application.state.backup_launcher = thread_launcher(application.state.maintenance)
    return application


app = create_app()
