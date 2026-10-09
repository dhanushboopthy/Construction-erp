"""GSP access: pick the adapter named by configuration."""

from functools import lru_cache

from app.core.config import GspProvider, get_settings
from app.services.gsp.base import GspClient, GspError
from app.services.gsp.fake import FakeGsp
from app.services.gsp.sandbox import SandboxGsp

__all__ = ["FakeGsp", "GspClient", "GspError", "get_client", "reset_client"]


@lru_cache
def _build() -> GspClient:
    settings = get_settings()
    if settings.gsp_provider is GspProvider.FAKE:
        if settings.is_production:
            raise GspError(
                "No GSP is configured. Set GSP_PROVIDER and the provider keys "
                "(a pretend provider is never used in production).",
                code="GSP_NOT_CONFIGURED",
            )
        return FakeGsp()
    return SandboxGsp(settings)


def get_client() -> GspClient:
    return _build()


def reset_client() -> None:
    _build.cache_clear()
