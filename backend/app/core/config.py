"""Application configuration, read from environment variables (see .env.example)."""

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class GspProvider(StrEnum):
    FAKE = "fake"
    SANDBOX = "sandbox"
    LIVE = "live"


_DEV_SECRET = "dev-only-secret-change-me-dev-only-secret"  # noqa: S105 - rejected in production


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Environment = Environment.DEVELOPMENT
    app_name: str = "Construction ERP"

    database_url: str = "postgresql+psycopg://erp:erp@localhost:5432/erp"
    db_pool_size: int = 5
    db_max_overflow: int = 5

    jwt_secret: str = _DEV_SECRET
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    refresh_token_hours: int = 12  # roughly one shop shift
    refresh_cookie_name: str = "erp_refresh"
    cookie_secure: bool = False
    # Escape hatch for a shop LAN served over plain HTTP. Prefer HTTPS (see docs/DEPLOYMENT.md).
    allow_insecure_cookies: bool = False

    login_max_attempts: int = 5
    login_lock_minutes: int = 15

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    enable_api_docs: bool = True

    # GSP for e-way bills and IRN (Milestone 10). "fake" only works outside production; "sandbox"
    # and "live" call the provider's HTTP API. Keys come from the environment, never the code.
    gsp_provider: GspProvider = GspProvider.FAKE
    gsp_base_url: str = ""
    gsp_client_id: str = ""
    gsp_client_secret: SecretStr = SecretStr("")
    gsp_username: str = ""
    gsp_password: SecretStr = SecretStr("")
    gsp_timeout_seconds: float = 20.0

    # Where uploaded files (weighbridge slips, delivery proof) are kept; back this folder up.
    storage_dir: str = "./data/files"
    max_upload_mb: int = 8

    log_level: str = "INFO"
    log_json: bool = False

    @property
    def is_production(self) -> bool:
        return self.app_env is Environment.PRODUCTION

    @model_validator(mode="after")
    def _check_production_safety(self) -> "Settings":
        if self.app_env is Environment.PRODUCTION:
            if self.jwt_secret == _DEV_SECRET or len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET must be set to a random value of 32+ characters")
            if not self.cookie_secure and not self.allow_insecure_cookies:
                raise ValueError(
                    "COOKIE_SECURE must be true in production (serve over HTTPS), "
                    "or set ALLOW_INSECURE_COOKIES=true for a plain-HTTP shop LAN"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
