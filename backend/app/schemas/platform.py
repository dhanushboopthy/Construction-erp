"""Duolink admin API shapes (Milestone 16, ADR 0012).

Counts, statuses and dates only: nothing here carries an amount, a cost or a document's contents
(test_platform_admin checks every field name).
"""

from datetime import datetime
from typing import Any

from pydantic import Field

from app.core.security import MIN_PASSWORD_LENGTH
from app.domain.plans import TrialState
from app.models.enums import PlatformAction, PlatformRole, Role, TenantPlan, TenantStatus
from app.schemas.common import Schema, StateCode
from app.schemas.user import Username

# ------------------------------------------------------------------ sign-in


class AdminLoginRequest(Schema):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=128)


class AdminOut(Schema):
    id: int
    email: str
    full_name: str
    mobile: str | None
    role: PlatformRole
    must_change_password: bool
    last_login_at: datetime | None


class AdminTokenResponse(Schema):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth token type, not a secret
    expires_in: int
    admin: AdminOut


class AdminChangePassword(Schema):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)


# ------------------------------------------------------------------ Duolink staff (M17)

EmailAddress = Field(min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MobileNumber = Field(default=None, max_length=20, pattern=r"^\+?[0-9 ]{7,15}$")


class StaffRow(Schema):
    id: int
    email: str
    full_name: str
    mobile: str | None
    role: PlatformRole
    is_active: bool
    locked: bool
    must_change_password: bool
    open_sessions: int
    last_login_at: datetime | None
    created_at: datetime


class StaffCreate(Schema):
    """The password is temporary: the new member must change it before anything else."""

    full_name: str = Field(min_length=1, max_length=100)
    email: str = EmailAddress
    mobile: str | None = MobileNumber
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)
    role: PlatformRole = PlatformRole.SUPPORT


class StaffUpdate(Schema):
    """Send only what changes. `mobile` sent as null clears it."""

    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    mobile: str | None = MobileNumber
    role: PlatformRole | None = None
    is_active: bool | None = None
    reason: str | None = Field(default=None, min_length=3, max_length=500)


# ------------------------------------------------------------------ companies


class TenantRow(Schema):
    id: int
    slug: str
    name: str
    status: TenantStatus
    plan: TenantPlan
    trial_ends_at: datetime | None
    trial_state: TrialState
    users: int  # active
    max_users: int  # the plan's, or the company's own
    locations: int  # active
    max_locations: int
    bills_30d: int  # sales bills issued in the last 30 days (a count, never an amount)
    last_sign_in_at: datetime | None
    created_at: datetime


class TenantDetail(TenantRow):
    own_max_users: int | None  # blank: the plan's limit applies
    own_max_locations: int | None
    suspended_at: datetime | None
    suspended_reason: str | None
    open_sessions: int


class TenantCreate(Schema):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=3, max_length=30, description="the subdomain: acme.duolink.app")
    plan: TenantPlan = TenantPlan.TRIAL
    state_code: StateCode
    owner_username: str = Username
    owner_full_name: str = Field(min_length=1, max_length=100)
    owner_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)


class TenantUpdate(Schema):
    """Send only what changes. `max_users` / `max_locations` sent as null go back to the plan's
    limit; `trial_ends_at` sent as null ends the trial period."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    plan: TenantPlan | None = None
    max_users: int | None = Field(default=None, ge=1, le=1000)
    max_locations: int | None = Field(default=None, ge=1, le=100)
    trial_ends_at: datetime | None = None


class SuspendRequest(Schema):
    reason: str = Field(min_length=3, max_length=500)


# ------------------------------------------------------------------ users across companies


class PlatformUserRow(Schema):
    id: int
    tenant_id: int
    tenant_slug: str
    tenant_name: str
    username: str
    full_name: str
    role: Role
    is_active: bool
    locked: bool
    failed_login_count: int
    last_login_at: datetime | None


class TemporaryPassword(Schema):
    """Shown once to the admin, who passes it to the user; the user should change it."""

    temporary_password: str


# ------------------------------------------------------------------ monitoring


class TrialEnding(Schema):
    id: int
    slug: str
    name: str
    trial_ends_at: datetime


class OverviewOut(Schema):
    tenants_total: int
    tenants_by_status: dict[TenantStatus, int]
    new_tenants_this_month: int
    active_users: int
    open_sessions: int
    sign_ins_24h: int
    sign_ins_7d: int
    failed_sign_ins_24h: int
    failed_sign_ins_7d: int
    trials_ending: list[TrialEnding]


class SignInEvent(Schema):
    at: datetime
    tenant_id: int
    tenant_slug: str
    username: str | None
    action: str  # login, login_failed, token_reuse
    ip: str | None


class PlatformAuditRow(Schema):
    id: int
    at: datetime
    admin_email: str | None
    action: PlatformAction
    tenant_slug: str | None
    target_user_id: int | None
    target_admin_email: str | None
    details: dict[str, Any] | None
    ip: str | None


# ------------------------------------------------------------------ the company's own view


class TenantPlanOut(Schema):
    plan: TenantPlan
    status: TenantStatus
    trial_ends_at: datetime | None
    users: int
    max_users: int
    locations: int
    max_locations: int
