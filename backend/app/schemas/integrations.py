"""Shapes for the shared integrations (Milestone 27). No answer carries a credential: a saved key
shows as its last 4 characters only. Credentials are accepted on the way in, never sent out."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, Field

from app.domain.gst import is_valid_gstin
from app.models.enums import IntegrationKind, IntegrationProvider, IntegrationStatus
from app.schemas.common import Schema

Secret = Annotated[str | None, Field(max_length=500)]


def _valid_gstin(value: str) -> str:
    value = value.upper()
    if not is_valid_gstin(value):
        raise ValueError("GSTIN is not valid (format or check digit)")
    return value


class GstinLookupIn(Schema):
    gstin: Annotated[
        str,
        AfterValidator(_valid_gstin),
        Field(description="15 characters, check digit verified"),
    ]


class GstinLookupOut(Schema):
    """Public registry data about a GSTIN, to fill a party or a company form."""

    gstin: str
    legal_name: str
    trade_name: str
    address: str
    state_code: str
    status: str  # as the registry words it: Active, Cancelled, Suspended
    fetched_at: datetime
    cached: bool
    # For a company: lookups left today, and whether it is near its limit. Blank for Duolink.
    lookups_left_today: int | None = None
    near_limit: bool = False


class IntegrationConnect(Schema):
    """Connect or update. A credential left blank keeps the saved one, so a key never has to
    be read back to change another setting."""

    provider: IntegrationProvider
    base_url: str = Field(default="", max_length=300)
    client_id: Secret = None
    client_secret: Secret = None
    username: Secret = None
    password: Secret = None
    api_key: Secret = None


class IntegrationLimitsIn(Schema):
    daily_limit: int = Field(ge=1, le=100_000)
    monthly_limit: int = Field(ge=1, le=100_000)
    warn_at_percent: int = Field(ge=1, le=100)
    cache_hours: int = Field(ge=0, le=8760)


class IntegrationOut(Schema):
    kind: IntegrationKind
    # What a Super Admin saved. Blank: not connected here, so `source` says what is used.
    provider: IntegrationProvider | None
    base_url: str
    key_last4: str | None
    status: IntegrationStatus
    # database: these settings; gsp_account: a lookup through the GSP's saved account;
    # environment: the GSP_* variables; none: nothing usable (a pretend provider in production).
    source: Literal["database", "gsp_account", "environment", "none"]
    effective_provider: IntegrationProvider | None
    credential_fields: list[str]  # what the sandbox and live providers ask for
    connected_at: datetime | None
    last_success_at: datetime | None
    last_failure_at: datetime | None
    last_failure_message: str | None
    daily_limit: int
    monthly_limit: int
    warn_at_percent: int
    cache_hours: int
    secret_key_set: bool  # INTEGRATION_SECRET_KEY is set, so keys can be saved


class IntegrationTestOut(Schema):
    ok: bool
    latency_ms: int | None
    error_code: str | None
    message: str | None
    integration: IntegrationOut


class OutcomeCounts(Schema):
    ok: int = 0
    failed: int = 0
    cached: int = 0
    blocked: int = 0
    total: int = 0


class IntegrationUsage(Schema):
    kind: IntegrationKind
    today: OutcomeCounts
    week: OutcomeCounts
    month: OutcomeCounts


class CompanyUsageRow(Schema):
    """Provider calls (ok and failed) count toward the limits; cached and blocked do not."""

    tenant_id: int
    slug: str
    name: str
    calls_today: int
    calls_month: int
    cached_month: int
    blocked_month: int
    failed_month: int
    near_limit: bool
    over_limit: bool


class IntegrationFailureRow(Schema):
    """A failed call: what was tried and the error code. Never a request or response body."""

    id: int
    at: datetime
    tenant_id: int | None
    tenant_name: str | None  # blank for a Duolink admin's own call
    operation: str
    error_code: str | None
    latency_ms: int | None
