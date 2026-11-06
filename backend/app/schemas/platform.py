"""Duolink admin API shapes (Milestone 16, ADR 0012).

Counts, statuses and dates only: nothing here carries an amount, a cost or a document's contents
(test_platform_admin checks every field name).
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field, ValidationInfo, field_validator

from app.core.security import MIN_PASSWORD_LENGTH
from app.domain.plans import TrialState
from app.models.enums import PlatformAction, PlatformRole, Role, TenantPlan, TenantStatus
from app.schemas.common import Cin, Gstin, Pan, Schema, StateCode
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
OptionalEmail = Field(default=None, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
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
    owner_name: str | None
    city: str | None
    state_code: str | None
    trial_ends_at: datetime | None
    trial_state: TrialState
    users: int  # active
    max_users: int  # the plan's, or the company's own
    locations: int  # active
    max_locations: int
    bills_30d: int  # sales bills issued in the last 30 days (a count, never an amount)
    last_sign_in_at: datetime | None
    last_activity_at: datetime | None  # any request at the company, to the minute
    created_at: datetime


class TenantDetail(TenantRow):
    own_max_users: int | None  # blank: the plan's limit applies
    own_max_locations: int | None
    suspended_at: datetime | None
    suspended_reason: str | None
    cancelled_at: datetime | None
    cancelled_reason: str | None
    owner_email: str | None
    owner_mobile: str | None
    notes: str | None  # internal: Duolink staff only, never shown to the company
    open_sessions: int


class TenantCreated(TenantDetail):
    sign_in_url: str  # where the owner signs in, e.g. https://acme.duolink.app


class TenantCreate(Schema):
    """One form, one transaction: the company, its seller details, its first shop and godown,
    the plan and the first owner. `registration_no` is the company's GSTIN."""

    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=3, max_length=30, description="the subdomain: acme.duolink.app")
    plan: TenantPlan = TenantPlan.TRIAL
    trial_days: int | None = Field(default=None, description="trial plan only; 14 if blank")
    start_active: bool = Field(default=False, description="skip the trial and start active")
    state_code: StateCode
    city: str | None = Field(default=None, max_length=100)
    legal_name: str | None = Field(default=None, min_length=1, max_length=200)  # blank: the name
    registration_no: Gstin = None
    shop_name: str = Field(default="Shop 1", min_length=1, max_length=100)
    shop_code: str = Field(default="S1", pattern=r"^[A-Z0-9]{1,2}$")
    owner_username: str = Username
    owner_full_name: str = Field(min_length=1, max_length=100)
    owner_email: str | None = OptionalEmail
    owner_mobile: str | None = MobileNumber
    owner_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)
    require_owner_password_change: bool = False

    @field_validator("registration_no")
    @classmethod
    def _gstin_matches_state(cls, value: str | None, info: ValidationInfo) -> str | None:
        state = info.data.get("state_code")
        if value and state and value[:2] != state:
            raise ValueError("The first two digits of the GSTIN must match the state code")
        return value


class TenantUpdate(Schema):
    """Send only what changes. `max_users` / `max_locations` sent as null go back to the plan's
    limit; `trial_ends_at` sent as null ends the trial period; the contact fields sent as null
    are cleared. The seller's legal details are changed through /seller-details."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    plan: TenantPlan | None = None
    max_users: int | None = Field(default=None, ge=1, le=1000)
    max_locations: int | None = Field(default=None, ge=1, le=100)
    trial_ends_at: datetime | None = None
    owner_name: str | None = Field(default=None, max_length=100)
    owner_email: str | None = OptionalEmail
    owner_mobile: str | None = MobileNumber
    city: str | None = Field(default=None, max_length=100)
    state_code: StateCode | None = None
    notes: str | None = Field(default=None, max_length=2000)


class SuspendRequest(Schema):
    reason: str = Field(min_length=3, max_length=500)


class CancelRequest(Schema):
    reason: str = Field(min_length=3, max_length=500)


class ReactivateRequest(Schema):
    """A reason is needed to reopen a cancelled company; a suspended one needs none."""

    reason: str | None = Field(default=None, min_length=3, max_length=500)


class SellerDetails(Schema):
    """What prints on the company's bills. `registration_no` is its GSTIN."""

    legal_name: str
    registration_no: str | None
    pan: str | None
    cin: str | None
    address: str
    state_code: str


class SellerDetailsUpdate(Schema):
    """Send only what changes; a blank `registration_no`, `pan` or `cin` clears it. A reason is
    always needed: these fields are on every bill."""

    legal_name: str | None = Field(default=None, min_length=1, max_length=200)
    registration_no: Gstin = None
    pan: Pan = None
    cin: Cin = None
    address: str | None = None
    state_code: StateCode | None = None
    reason: str = Field(min_length=3, max_length=500)


class TenantUsage(Schema):
    """Counts only (ADR 0012): no amounts."""

    users: int
    shops: int
    bills_7d: int
    bills_30d: int
    bills_90d: int
    purchases_30d: int
    attachments: int
    attachment_bytes: int


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
    mobile: str | None
    must_change_password: bool
    removed_at: datetime | None


class PlatformUserUpdate(Schema):
    """Send only what changes. `mobile` sent as null clears it. A reason is always needed."""

    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    mobile: str | None = MobileNumber
    username: str | None = Field(default=None, pattern=r"^[a-z0-9_.-]{3,50}$")
    role: Role | None = None
    reason: str = Field(min_length=3, max_length=500)


class RemoveUserRequest(Schema):
    """`confirm_username` must be the user's username, typed exactly."""

    confirm_username: str = Field(max_length=50)
    reason: str = Field(min_length=3, max_length=500)


class UserSessionRow(Schema):
    id: uuid.UUID
    device: str
    user_agent: str | None
    ip: str | None
    signed_in_at: datetime
    last_used_at: datetime
    expires_at: datetime


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
