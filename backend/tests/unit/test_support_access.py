"""Owner-granted support access: grant windows, liveness, token expiry, what a support session
may do and why it is refused (Milestone 23)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.support_access import (
    EVENT_RETENTION_DAYS,
    EXIT_PATH,
    GRANT_HOURS,
    TOKEN_HOURS,
    GrantState,
    Refusal,
    SupportAccessError,
    effective_end,
    event_retention_cutoff,
    grant_state,
    grant_window,
    is_live,
    refusal,
    seconds_left,
    session_is_open,
    session_is_stale,
    support_may,
    token_expiry,
)

T0 = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)


def test_the_fixed_choices():
    assert GRANT_HOURS == (1, 4, 24, 72)
    assert TOKEN_HOURS == 2
    assert EVENT_RETENTION_DAYS == 365
    assert EXIT_PATH == "/api/v1/support-session/exit"


@pytest.mark.parametrize("hours", [1, 4, 24, 72])
def test_a_grant_starts_now_and_lasts_the_chosen_hours(hours):
    assert grant_window(T0, hours) == (T0, T0 + timedelta(hours=hours))


@pytest.mark.parametrize("hours", [0, 2, 48, 73, -1])
def test_any_other_duration_is_refused(hours):
    with pytest.raises(SupportAccessError) as caught:
        grant_window(T0, hours)
    assert caught.value.code == "GRANT_DURATION_INVALID"
    assert "1, 4, 24 or 72" in str(caught.value)


def test_a_grant_is_live_from_its_start_until_just_before_its_end():
    start, end = T0, T0 + 4 * HOUR
    assert grant_state(start, end, None, T0) is GrantState.LIVE
    assert grant_state(start, end, None, end - timedelta(seconds=1)) is GrantState.LIVE
    assert grant_state(start, end, None, end) is GrantState.ENDED
    assert grant_state(start, end, None, T0 - timedelta(seconds=1)) is GrantState.NOT_STARTED
    assert is_live(start, end, None, T0) and not is_live(start, end, None, end)


def test_a_revoked_grant_is_revoked_even_before_its_end():
    assert grant_state(T0, T0 + 4 * HOUR, T0 + HOUR, T0 + 2 * HOUR) is GrantState.REVOKED
    assert not is_live(T0, T0 + 4 * HOUR, T0 + HOUR, T0 + 2 * HOUR)


def test_a_support_token_lasts_two_hours_or_until_the_grant_ends_whichever_is_first():
    assert token_expiry(T0, T0 + 72 * HOUR) == T0 + 2 * HOUR
    assert token_expiry(T0, T0 + HOUR) == T0 + HOUR
    assert token_expiry(T0, T0 + 2 * HOUR) == T0 + 2 * HOUR


def test_seconds_left_never_goes_below_zero():
    assert seconds_left(T0 + HOUR, T0) == 3600
    assert seconds_left(T0 + timedelta(seconds=90, microseconds=900), T0) == 90
    assert seconds_left(T0, T0 + HOUR) == 0


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_a_support_session_reads(method):
    assert support_may(method, "/api/v1/invoices")


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_a_support_session_writes_nothing(method):
    assert not support_may(method, "/api/v1/invoices")
    assert not support_may(method, "/api/v1/auth/change-password")
    assert not support_may(method, "/api/v1/support-access/revoke")


def test_the_one_write_is_leaving_the_session():
    assert support_may("POST", EXIT_PATH)
    assert not support_may("DELETE", EXIT_PATH)
    assert not support_may("POST", EXIT_PATH + "/")
    assert not support_may("POST", "/api/v1/support-session/exit/x")


def _refusal(**changes):
    facts = {
        "token_tenant_id": 1,
        "tenant_id": 1,
        "session_found": True,
        "session_ended": False,
        "grant_state": GrantState.LIVE,
        "admin_may_enter": True,
    }
    return refusal(**(facts | changes))


def test_a_live_session_at_its_own_company_is_not_refused():
    assert _refusal() is None


def test_why_a_support_request_is_refused_first_reason_wins():
    assert _refusal(tenant_id=2) is Refusal.WRONG_COMPANY
    assert _refusal(tenant_id=2, session_found=False) is Refusal.WRONG_COMPANY
    assert _refusal(session_found=False) is Refusal.SESSION_NOT_FOUND
    assert _refusal(session_ended=True, grant_state=GrantState.REVOKED) is Refusal.SESSION_ENDED
    assert _refusal(grant_state=GrantState.REVOKED) is Refusal.GRANT_REVOKED
    assert _refusal(grant_state=GrantState.ENDED) is Refusal.GRANT_ENDED
    assert _refusal(grant_state=GrantState.NOT_STARTED) is Refusal.GRANT_ENDED
    assert _refusal(admin_may_enter=False) is Refusal.ADMIN_NOT_ALLOWED


def test_which_refusals_end_the_session_in_the_database():
    assert Refusal.GRANT_REVOKED.ends_session and Refusal.GRANT_ENDED.ends_session
    assert Refusal.ADMIN_NOT_ALLOWED.ends_session
    assert not Refusal.WRONG_COMPANY.ends_session  # it is not this company's session
    assert not Refusal.SESSION_NOT_FOUND.ends_session
    assert not Refusal.SESSION_ENDED.ends_session  # already ended


def test_a_session_is_open_until_it_ends_or_its_token_expires():
    expires = T0 + 2 * HOUR
    assert session_is_open(None, expires, T0 + HOUR)
    assert not session_is_open(None, expires, expires)
    assert not session_is_open(T0 + HOUR, expires, T0 + HOUR)


def test_a_stale_session_is_one_never_ended_whose_token_has_expired():
    expires = T0 + 2 * HOUR
    assert session_is_stale(None, expires, expires)
    assert not session_is_stale(None, expires, T0)
    assert not session_is_stale(T0 + HOUR, expires, expires + HOUR)


def test_the_effective_end_of_a_session():
    expires = T0 + 2 * HOUR
    assert effective_end(T0 + HOUR, expires, T0 + 5 * HOUR) == T0 + HOUR  # it ended
    assert effective_end(None, expires, T0 + 5 * HOUR) == expires  # its token ran out
    assert effective_end(None, expires, T0 + HOUR) is None  # still open


def test_events_are_kept_for_a_year():
    assert event_retention_cutoff(T0) == T0 - timedelta(days=365)
