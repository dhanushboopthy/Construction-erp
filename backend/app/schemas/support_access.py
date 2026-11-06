"""Owner-granted support access (Milestone 23, ADR 0013).

The company's shapes (its owner's Settings) and Duolink's (the admin). Duolink's shapes carry
statuses, times and counts only; whether the owner showed cost and margin is
`owner_only_figures`, named so the admin's money-field test stays strict.
"""

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.models.enums import SupportSessionEnd
from app.schemas.common import Schema

GrantHours = Literal[1, 4, 24, 72]
GrantStatus = Literal["live", "revoked", "ended"]
SessionStatus = Literal["open", "ended", "stale"]


# ---------------------------------------------------------------- the company's side


class GrantCreate(Schema):
    duration_hours: GrantHours
    include_costs: bool = False
    reason: str = Field(min_length=3, max_length=300)
    ticket_id: int | None = None


class GrantOut(Schema):
    id: int
    status: GrantStatus
    starts_at: datetime
    ends_at: datetime
    seconds_left: int
    include_costs: bool
    reason: str
    ticket_id: int | None
    ticket_number: str | None
    granted_by_name: str
    revoked_at: datetime | None
    revoked_by_name: str | None


class AccessOverview(Schema):
    live: GrantOut | None
    recent: list[GrantOut]  # the last grants, newest first
    durations: list[int]


class SessionRow(Schema):
    """One visit by Duolink, as the owner's history shows it."""

    id: int
    grant_id: int
    admin_name: str
    reason: str
    status: SessionStatus
    started_at: datetime
    ended_at: datetime | None  # when it ended, or when its token ran out
    end_reason: SupportSessionEnd | None
    request_count: int
    include_costs: bool


class SessionEventOut(Schema):
    at: datetime
    method: str
    path: str
    refused: bool


class SupportSessionStatus(Schema):
    """What the banner shows to the Duolink admin inside the company."""

    session_id: int
    company_name: str
    admin_name: str
    started_at: datetime
    expires_at: datetime  # the earlier of the token's two hours and the grant's end
    grant_ends_at: datetime
    include_costs: bool
    read_only: Literal[True] = True


# ---------------------------------------------------------------- Duolink's side


class EnterRequest(Schema):
    reason: str = Field(min_length=3, max_length=300)


class SupportSessionStarted(Schema):
    session_id: int
    token: str
    expires_at: datetime
    entry_url: str  # https://<slug>.<domain>/support-entry#token=...: a fragment, never logged


class AdminAccessStatus(Schema):
    live: bool
    grant_id: int | None
    starts_at: datetime | None
    ends_at: datetime | None
    seconds_left: int
    owner_only_figures: bool  # the owner ticked "show cost and margin"
    reason: str | None
    ticket_number: str | None
    granted_by_name: str | None
    open_sessions: int


class AdminSessionRow(Schema):
    id: int
    tenant_id: int
    tenant_slug: str
    tenant_name: str
    admin_id: int
    admin_name: str
    reason: str
    status: SessionStatus
    started_at: datetime
    expires_at: datetime
    ended_at: datetime | None
    end_reason: SupportSessionEnd | None
    request_count: int
    owner_only_figures: bool


class AdminSessionPage(Schema):
    items: list[AdminSessionRow]
    total: int
    open: int
    stale: int  # never ended, token expired: shown in the bell (M24)
    limit: int
    offset: int
