"""GSP access: build the adapter from whichever settings are set (Milestone 27).

1. The Duolink admin's saved settings (`platform_integration`, credentials decrypted with
   INTEGRATION_SECRET_KEY) win.
2. The environment (GSP_PROVIDER, GSP_BASE_URL, ...) is the fallback, for a single-shop install.

A GSTIN lookup uses its own saved settings, else the GSP account's, else the environment: most
GSPs offer the taxpayer search on the same account.
"""

from dataclasses import fields
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import GspProvider, Settings, get_settings
from app.core.crypto import IntegrationKeyError, decrypt_json
from app.models.enums import IntegrationKind
from app.models.integrations import PlatformIntegration
from app.services.gsp.base import GspClient, GspConfig, GspError, TaxpayerInfo
from app.services.gsp.fake import FakeGsp
from app.services.gsp.sandbox import SandboxGsp

__all__ = [
    "FakeGsp",
    "GspClient",
    "GspConfig",
    "GspError",
    "TaxpayerInfo",
    "client_for",
    "env_config",
    "get_client",
    "reset_client",
    "resolve",
    "saved_config",
]

_CREDENTIAL_FIELDS = frozenset(f.name for f in fields(GspConfig)) - {
    "provider",
    "source",
    "base_url",
    "timeout_seconds",
}


@lru_cache(maxsize=16)
def _build(config: GspConfig) -> GspClient:
    if config.provider == GspProvider.FAKE.value:
        if get_settings().is_production:
            raise GspError(
                "No GSP is configured. Connect one in the Duolink admin, or set GSP_PROVIDER "
                "and the provider keys (a pretend provider is never used in production).",
                code="GSP_NOT_CONFIGURED",
            )
        return FakeGsp(source=config.source)
    return SandboxGsp(config)


def env_config(settings: Settings | None = None) -> GspConfig:
    s = settings or get_settings()
    return GspConfig(
        provider=s.gsp_provider.value,
        source="environment",
        base_url=s.gsp_base_url,
        timeout_seconds=s.gsp_timeout_seconds,
        client_id=s.gsp_client_id,
        client_secret=s.gsp_client_secret.get_secret_value(),
        username=s.gsp_username,
        password=s.gsp_password.get_secret_value(),
    )


def saved_config(db: Session, kind: IntegrationKind) -> GspConfig | None:
    """The admin's saved settings for this kind, or None if it is not connected."""
    row = db.execute(
        select(PlatformIntegration).where(PlatformIntegration.kind == kind)
    ).scalar_one_or_none()
    if row is None or row.provider is None:
        return None
    settings = get_settings()
    try:
        saved = (
            decrypt_json(row.credentials, settings.integration_secret_key.get_secret_value())
            if row.credentials
            else {}
        )
    except IntegrationKeyError as exc:
        raise GspError(exc.message, code=exc.code) from exc
    return GspConfig(
        provider=row.provider.value,
        source="database",
        base_url=row.base_url,
        timeout_seconds=settings.gsp_timeout_seconds,
        **{k: v for k, v in saved.items() if k in _CREDENTIAL_FIELDS},
    )


def resolve(db: Session, kind: IntegrationKind = IntegrationKind.GSP) -> GspConfig:
    config = saved_config(db, kind)
    if config is None and kind is IntegrationKind.GSTIN_LOOKUP:
        config = saved_config(db, IntegrationKind.GSP)
    return config or env_config()


def client_for(config: GspConfig) -> GspClient:
    return _build(config)


def get_client(db: Session | None = None, kind: IntegrationKind = IntegrationKind.GSP) -> GspClient:
    """The client to call. Without a session only the environment is read."""
    return _build(resolve(db, kind) if db is not None else env_config())


def reset_client() -> None:
    _build.cache_clear()
