"""Shared integrations (GSP and GSTIN lookup): credentials, limits, the cache and usage windows
(Milestone 27). Pure rules, no database."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domain.integrations import (
    COUNTED,
    FAILURE_MESSAGE_LENGTH,
    KINDS,
    OUTCOMES,
    PROVIDERS,
    STATUSES,
    IntegrationRuleError,
    Limits,
    check_base_url,
    check_limits,
    check_provider,
    credential_fields,
    is_fresh,
    key_field,
    key_last4,
    lookup_decision,
    merge_credentials,
    near_limit,
    remaining,
    scrub,
    status_of,
    usage_windows,
)

IST = ZoneInfo("Asia/Kolkata")
T0 = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
LIMITS = Limits(daily=5, monthly=20, warn_at_percent=80, cache_hours=24)
GSP_CREDS = {
    "client_id": "duolink-client",
    "client_secret": "s3cret-client-9876",
    "username": "duolink",
    "password": "portal-pass-123",
}


def _code(call):
    with pytest.raises(IntegrationRuleError) as caught:
        call()
    return caught.value.code


def test_the_vocabularies():
    assert KINDS == ("gsp", "gstin_lookup")
    assert PROVIDERS == ("fake", "sandbox", "live")
    assert OUTCOMES == ("ok", "failed", "cached", "blocked")
    assert STATUSES == ("not_connected", "connected", "failing")
    # Only a call that reached the provider uses up a company's allowance.
    assert frozenset({"ok", "failed"}) == COUNTED


# ------------------------------------------------------------------ credentials


def test_which_credentials_each_kind_needs():
    assert credential_fields("gsp", "sandbox") == (
        "client_id",
        "client_secret",
        "username",
        "password",
    )
    assert credential_fields("gsp", "live") == credential_fields("gsp", "sandbox")
    assert credential_fields("gstin_lookup", "live") == ("api_key",)
    assert credential_fields("gsp", "fake") == ()  # the pretend provider needs no keys
    assert key_field("gsp") == "client_secret" and key_field("gstin_lookup") == "api_key"
    assert _code(lambda: credential_fields("tally", "live")) == "INTEGRATION_KIND_UNKNOWN"
    assert _code(lambda: credential_fields("gsp", "magic")) == "PROVIDER_UNKNOWN"


def test_new_credentials_must_be_complete():
    assert merge_credentials("gsp", "sandbox", {}, GSP_CREDS) == GSP_CREDS
    error = IntegrationRuleError
    with pytest.raises(error) as caught:
        merge_credentials("gsp", "sandbox", {}, {"client_id": "x", "client_secret": "y" * 8})
    assert caught.value.code == "CREDENTIALS_MISSING" and caught.value.field == "username"


def test_a_blank_field_keeps_the_saved_value_so_a_key_is_never_typed_back():
    stored = dict(GSP_CREDS)
    merged = merge_credentials(
        "gsp", "live", stored, {"client_secret": "", "password": "new-pass-456", "username": " "}
    )
    assert merged == GSP_CREDS | {"password": "new-pass-456"}
    # Values are trimmed; fields the provider does not use are dropped.
    assert merge_credentials(
        "gstin_lookup", "sandbox", {}, {"api_key": "  abcd-1234-wxyz  ", "username": "nobody"}
    ) == {"api_key": "abcd-1234-wxyz"}
    assert merge_credentials("gsp", "fake", GSP_CREDS, {}) == {}


def test_the_key_must_be_long_enough_that_its_last_four_give_nothing_away():
    with pytest.raises(IntegrationRuleError) as caught:
        merge_credentials("gstin_lookup", "live", {}, {"api_key": "short"})
    assert caught.value.code == "KEY_TOO_SHORT" and caught.value.field == "api_key"
    assert key_last4("abcd-1234-wxyz") == "wxyz"
    assert _code(lambda: key_last4("1234567")) == "KEY_TOO_SHORT"


def test_the_base_url():
    assert check_base_url("fake", "https://ignored.example") == ""
    assert check_base_url("sandbox", " http://localhost:9000/api/ ") == "http://localhost:9000/api"
    assert check_base_url("live", "https://gsp.example/v1") == "https://gsp.example/v1"
    assert _code(lambda: check_base_url("sandbox", "")) == "BASE_URL_REQUIRED"
    assert _code(lambda: check_base_url("sandbox", "ftp://gsp.example")) == "BASE_URL_INVALID"
    assert _code(lambda: check_base_url("live", "http://gsp.example")) == "BASE_URL_NOT_HTTPS"
    assert _code(lambda: check_base_url("live", "https://")) == "BASE_URL_INVALID"


def test_the_pretend_provider_is_refused_in_production():
    check_provider("fake", is_production=False)
    check_provider("live", is_production=True)
    assert _code(lambda: check_provider("fake", is_production=True)) == "FAKE_NOT_IN_PRODUCTION"
    assert _code(lambda: check_provider("other", is_production=False)) == "PROVIDER_UNKNOWN"


def test_a_failure_message_is_trimmed_and_never_carries_a_secret():
    message = "Login refused for duolink with   s3cret-client-9876\n(try again)"
    # Every saved credential is hidden, the username too.
    assert scrub(message, GSP_CREDS.values()) == "Login refused for **** with **** (try again)"
    assert len(scrub("x" * 500, [])) == FAILURE_MESSAGE_LENGTH
    assert scrub("abc", ["", "ab"]) == "abc"  # too short to be a secret worth hiding
    assert scrub("   ", []) == ""


# ------------------------------------------------------------------ limits and status


def test_limits_are_checked():
    assert check_limits(LIMITS) == LIMITS
    assert check_limits(Limits(daily=1, monthly=1, warn_at_percent=100, cache_hours=0))
    for bad, field in (
        (Limits(daily=0, monthly=20, warn_at_percent=80, cache_hours=24), "daily"),
        (Limits(daily=5, monthly=100_001, warn_at_percent=80, cache_hours=24), "monthly"),
        (Limits(daily=5, monthly=20, warn_at_percent=0, cache_hours=24), "warn_at_percent"),
        (Limits(daily=5, monthly=20, warn_at_percent=101, cache_hours=24), "warn_at_percent"),
        (Limits(daily=5, monthly=20, warn_at_percent=80, cache_hours=-1), "cache_hours"),
        (Limits(daily=5, monthly=20, warn_at_percent=80, cache_hours=8761), "cache_hours"),
    ):
        with pytest.raises(IntegrationRuleError) as caught:
            check_limits(bad)
        assert caught.value.code == "LIMIT_INVALID" and caught.value.field == field
    with pytest.raises(IntegrationRuleError) as caught:
        check_limits(Limits(daily=30, monthly=20, warn_at_percent=80, cache_hours=24))
    assert caught.value.code == "LIMIT_DAILY_OVER_MONTHLY"


def test_the_status_follows_the_last_outcome():
    later = T0 + timedelta(minutes=5)
    assert status_of(connected=False, last_success_at=T0, last_failure_at=None) == "not_connected"
    assert status_of(connected=True, last_success_at=None, last_failure_at=None) == "connected"
    assert status_of(connected=True, last_success_at=T0, last_failure_at=later) == "failing"
    assert status_of(connected=True, last_success_at=later, last_failure_at=T0) == "connected"
    assert status_of(connected=True, last_success_at=None, last_failure_at=T0) == "failing"


def test_near_and_over_the_limit():
    assert not near_limit(3, 5, 80)
    assert near_limit(4, 5, 80)
    assert near_limit(9, 5, 80)
    assert remaining(3, 5) == 2 and remaining(7, 5) == 0


# ------------------------------------------------------------------ the lookup


def test_a_cached_answer_is_fresh_for_the_cache_hours():
    assert is_fresh(T0, T0 + timedelta(hours=23, minutes=59), 24)
    assert not is_fresh(T0, T0 + timedelta(hours=24), 24)
    assert not is_fresh(T0, T0, 0)  # zero hours: never cached
    assert not is_fresh(None, T0, 24)


def test_a_lookup_is_served_from_the_cache_then_refused_over_the_limit():
    assert lookup_decision(fresh=True, used_today=99, used_month=99, limits=LIMITS) == "cached"
    assert lookup_decision(fresh=False, used_today=4, used_month=19, limits=LIMITS) == "call"
    assert lookup_decision(fresh=False, used_today=5, used_month=5, limits=LIMITS) == "blocked"
    assert lookup_decision(fresh=False, used_today=0, used_month=20, limits=LIMITS) == "blocked"


def test_usage_windows_are_indian_calendar_days_weeks_and_months():
    windows = usage_windows(date(2026, 11, 4), IST)  # a Wednesday
    assert windows.day == datetime(2026, 11, 4, tzinfo=IST)
    assert windows.week == datetime(2026, 11, 2, tzinfo=IST)  # the Monday
    assert windows.month == datetime(2026, 11, 1, tzinfo=IST)
    assert windows.day.astimezone(UTC) == datetime(2026, 11, 3, 18, 30, tzinfo=UTC)
    early = usage_windows(date(2026, 12, 1), IST)  # a Tuesday: the week began last month
    assert early.week == datetime(2026, 11, 30, tzinfo=IST)
    assert early.month == datetime(2026, 12, 1, tzinfo=IST)
