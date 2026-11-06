"""Application configuration, read from environment variables (see .env.example)."""

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.crypto import IntegrationKeyError, check_key


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"  # a copy for training and trials: every PDF is stamped TEST
    PRODUCTION = "production"


class GspProvider(StrEnum):
    FAKE = "fake"
    SANDBOX = "sandbox"
    LIVE = "live"


class RazorpayProvider(StrEnum):
    LIVE = "live"  # Razorpay's HTTP API; test keys (rzp_test_...) use its test mode
    FAKE = "fake"  # a pretend gateway for development and tests; refused in production


class StorageProvider(StrEnum):
    LOCAL = "local"  # a folder on the server (development, or a volume that is backed up)
    S3 = "s3"  # any S3-compatible bucket: AWS S3, Cloudflare R2, Backblaze B2, MinIO, Wasabi


_DEV_SECRET = "dev-only-secret-change-me-dev-only-secret"  # noqa: S105 - rejected in production


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Environment = Environment.DEVELOPMENT
    app_name: str = "Construction ERP"

    database_url: str = "postgresql+psycopg://erp:erp@localhost:5432/erp"
    db_pool_size: int = 5
    db_max_overflow: int = 5
    # The app's connections switch to this role, which has no superuser rights, so PostgreSQL
    # row-level security applies to them (migration 0024 creates it). Migrations keep running
    # as the owner. Blank turns the switch off (not for production).
    db_app_role: str = "erp_app"

    # Companies by subdomain (ADR 0011): acme.<BASE_DOMAIN> is the company "acme". Any other
    # host (the bare domain, an IP address on a shop LAN) uses DEFAULT_TENANT_SLUG; leave that
    # blank on a SaaS server so only real subdomains reach a company.
    base_domain: str = "localhost"
    default_tenant_slug: str = "main"
    admin_subdomain: str = "admin"
    # A small install with one domain and no admin.<domain> record: let the Duolink admin sign in
    # on the company's own address (the sign-in page sends an email to the admin API, and the
    # console lives at /admin). Off by default: ADR 0012 keeps the console on its own host.
    admin_on_main_host: bool = False

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
    # Milestone 27: provider keys saved from the Duolink admin are encrypted with this Fernet
    # key. Settings saved there win over the GSP_* variables above, which stay the fallback for
    # a single-shop install. The app refuses to start if saved keys exist and this is blank.
    integration_secret_key: SecretStr = SecretStr("")

    # Online renewal through Razorpay (Milestone 30). Off unless both keys are set: owners are
    # then told to contact Duolink, as in Milestone 21. The key id is the public half that
    # Razorpay Checkout needs in the browser; the key secret and the webhook secret never leave
    # the server. The webhook secret is optional: without it the webhook answers 404.
    razorpay_provider: RazorpayProvider = RazorpayProvider.LIVE
    razorpay_key_id: SecretStr = SecretStr("")
    razorpay_key_secret: SecretStr = SecretStr("")
    razorpay_webhook_secret: SecretStr = SecretStr("")
    razorpay_base_url: str = "https://api.razorpay.com/v1"
    razorpay_timeout_seconds: float = 15.0

    # Where uploaded files (weighbridge slips, delivery proof) are kept; back this folder up.
    storage_provider: StorageProvider = StorageProvider.LOCAL
    storage_dir: str = "./data/files"
    s3_bucket: str = ""
    s3_endpoint_url: str = ""  # blank for AWS S3
    s3_region: str = "ap-south-1"
    s3_access_key_id: str = ""
    s3_secret_access_key: SecretStr = SecretStr("")
    s3_prefix: str = ""
    max_upload_mb: int = 8

    # Where the nightly backups land (the backup container's folder, mounted read-only here).
    backup_dir: str = ""
    # Where pg_dump and pg_restore live when they are not in a system folder (Milestone 25).
    pg_bin_dir: str = ""
    backup_tool_timeout_seconds: int = 1800
    app_version: str = "1.0.0"
    # Which build of the backend is running (Milestone 29), e.g. the git commit it was built
    # from. The admin's "App and updates" page shows it next to the frontend's. Blank: "dev".
    app_build: str = ""

    log_level: str = "INFO"
    log_json: bool = False

    @property
    def is_production(self) -> bool:
        return self.app_env is Environment.PRODUCTION

    @property
    def online_renewal_enabled(self) -> bool:
        """Owners may renew online: both Razorpay keys are set (Milestone 30)."""
        return bool(
            self.razorpay_key_id.get_secret_value() and self.razorpay_key_secret.get_secret_value()
        )

    @model_validator(mode="after")
    def _check_production_safety(self) -> "Settings":
        try:
            check_key(self.integration_secret_key.get_secret_value())
        except IntegrationKeyError as exc:
            raise ValueError(exc.message) from exc
        if self.app_env is Environment.PRODUCTION:
            if self.jwt_secret == _DEV_SECRET or len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET must be set to a random value of 32+ characters")
            if not self.cookie_secure and not self.allow_insecure_cookies:
                raise ValueError(
                    "COOKIE_SECURE must be true in production (serve over HTTPS), "
                    "or set ALLOW_INSECURE_COOKIES=true for a plain-HTTP shop LAN"
                )
            if not self.db_app_role:
                raise ValueError("DB_APP_ROLE must be set in production (row-level security)")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
