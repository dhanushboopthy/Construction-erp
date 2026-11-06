"""Owner-granted support access, "Login as Company" with consent (Milestone 23, ADR 0013).

Pure rules. The company owner grants Duolink access for a fixed time; while the grant is live a
Super Admin may open a read-only support session at that company. Every request of the session is
checked again: a revoked or ended grant, an ended session or a token used at another company is
refused at once. No clock here: `now` is passed in.
"""

from datetime import datetime, timedelta
from enum import StrEnum

GRANT_HOURS = (1, 4, 24, 72)  # the owner's choices
TOKEN_HOURS = 2  # a support token never outlives this, nor the grant
EVENT_RETENTION_DAYS = 365  # each request of a session is kept at least this long
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
EXIT_PATH = "/api/v1/support-session/exit"  # the only write a support session may make


class SupportAccessError(ValueError):
    """The support access rules refuse this. `code` is the API error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class GrantState(StrEnum):
    NOT_STARTED = "not_started"
    LIVE = "live"
    REVOKED = "revoked"
    ENDED = "ended"


class Refusal(StrEnum):
    """Why a request under a support token is refused (every one answers 401)."""

    WRONG_COMPANY = "wrong_company"
    SESSION_NOT_FOUND = "session_not_found"
    SESSION_ENDED = "session_ended"
    GRANT_REVOKED = "grant_revoked"
    GRANT_ENDED = "grant_ended"
    ADMIN_NOT_ALLOWED = "admin_not_allowed"

    @property
    def ends_session(self) -> bool:
        """The session is still open in the database and must be closed now."""
        return self in {Refusal.GRANT_REVOKED, Refusal.GRANT_ENDED, Refusal.ADMIN_NOT_ALLOWED}


def grant_window(now: datetime, hours: int) -> tuple[datetime, datetime]:
    """A grant starts when the owner gives it and lasts one of the fixed choices."""
    if hours not in GRANT_HOURS:
        raise SupportAccessError(
            "GRANT_DURATION_INVALID", "Support access lasts 1, 4, 24 or 72 hours."
        )
    return now, now + timedelta(hours=hours)


def grant_state(
    starts_at: datetime, ends_at: datetime, revoked_at: datetime | None, now: datetime
) -> GrantState:
    if revoked_at is not None:
        return GrantState.REVOKED
    if now < starts_at:
        return GrantState.NOT_STARTED
    if now >= ends_at:
        return GrantState.ENDED
    return GrantState.LIVE


def is_live(
    starts_at: datetime, ends_at: datetime, revoked_at: datetime | None, now: datetime
) -> bool:
    return grant_state(starts_at, ends_at, revoked_at, now) is GrantState.LIVE


def token_expiry(now: datetime, grant_ends_at: datetime) -> datetime:
    """The earlier of two hours from now and the grant's end."""
    return min(now + timedelta(hours=TOKEN_HOURS), grant_ends_at)


def seconds_left(ends_at: datetime, now: datetime) -> int:
    return max(0, int((ends_at - now).total_seconds()))


def support_may(method: str, path: str) -> bool:
    """A support session reads, and its one write is leaving. Everything else is 403
    SUPPORT_READ_ONLY: no saving, no password or user change, no change to the grant."""
    return method in SAFE_METHODS or (method == "POST" and path == EXIT_PATH)


def refusal(
    *,
    token_tenant_id: int,
    tenant_id: int,
    session_found: bool,
    session_ended: bool,
    grant_state: GrantState,
    admin_may_enter: bool,
) -> Refusal | None:
    """Why this request under a support token must be refused, or None. Checked on every
    request, so a revoke takes effect on the next one."""
    if token_tenant_id != tenant_id:
        return Refusal.WRONG_COMPANY
    if not session_found:
        return Refusal.SESSION_NOT_FOUND
    if session_ended:
        return Refusal.SESSION_ENDED
    if grant_state is GrantState.REVOKED:
        return Refusal.GRANT_REVOKED
    if grant_state is not GrantState.LIVE:
        return Refusal.GRANT_ENDED
    if not admin_may_enter:
        return Refusal.ADMIN_NOT_ALLOWED
    return None


def session_is_open(ended_at: datetime | None, expires_at: datetime, now: datetime) -> bool:
    return ended_at is None and now < expires_at


def session_is_stale(ended_at: datetime | None, expires_at: datetime, now: datetime) -> bool:
    """Never ended, but its token has run out: the admin closed the tab without leaving."""
    return ended_at is None and now >= expires_at


def effective_end(
    ended_at: datetime | None, expires_at: datetime, now: datetime
) -> datetime | None:
    """When the session stopped being usable: when it ended, else when its token ran out, else
    None while it is still open."""
    if ended_at is not None:
        return ended_at
    return expires_at if now >= expires_at else None


def event_retention_cutoff(now: datetime) -> datetime:
    """Request events older than this may be pruned; younger ones are kept."""
    return now - timedelta(days=EVENT_RETENTION_DAYS)
