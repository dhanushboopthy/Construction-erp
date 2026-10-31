"""M19: the rules behind the Duolink user support tools (domain/user_support.py)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain import user_support as rules

NOW = datetime(2026, 11, 1, 10, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("typed", "expected", "ok"),
    [
        ("ravi", "ravi", True),
        ("Ravi", "ravi", False),  # case-sensitive
        ("ravi ", "ravi", False),  # nothing is trimmed for the caller
        ("", "ravi", False),
        ("rav", "ravi", False),
    ],
)
def test_the_typed_username_must_match_exactly(typed, expected, ok):
    assert rules.confirmation_matches(typed, expected) is ok


def test_the_last_active_owner_cannot_be_removed():
    with pytest.raises(rules.UserRuleError) as err:
        rules.check_removal(is_owner=True, is_active=True, active_owners=1)
    assert err.value.code == "LAST_OWNER"


def test_an_owner_can_be_removed_when_another_owner_is_active():
    rules.check_removal(is_owner=True, is_active=True, active_owners=2)


def test_a_counter_user_can_always_be_removed():
    rules.check_removal(is_owner=False, is_active=True, active_owners=1)


def test_an_inactive_owner_does_not_count_as_the_last_one():
    rules.check_removal(is_owner=True, is_active=False, active_owners=1)


def test_a_removed_account_is_refused_further_changes():
    with pytest.raises(rules.UserRuleError) as err:
        rules.check_not_removed(NOW)
    assert err.value.code == "USER_REMOVED"
    rules.check_not_removed(None)


@pytest.mark.parametrize(
    ("revoked", "expires", "live"),
    [
        (None, NOW + timedelta(hours=1), True),
        (None, NOW, False),  # runs out exactly now
        (None, NOW - timedelta(seconds=1), False),
        (NOW - timedelta(hours=1), NOW + timedelta(hours=1), False),  # signed out
    ],
)
def test_a_session_is_live_until_it_expires_or_is_revoked(revoked, expires, live):
    assert rules.session_is_live(revoked, expires, NOW) is live


@pytest.mark.parametrize(
    ("agent", "label"),
    [
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36",
            "Chrome on Windows",
        ),
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
            "Edge on Windows",
        ),
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
            "Firefox on Windows",
        ),
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/17.5 Safari/605.1.15",
            "Safari on macOS",
        ),
        (
            "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Mobile Safari/537.36",
            "Chrome on Android",
        ),
        (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
            "Safari on iPhone",
        ),
        (
            "Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
            "Safari on iPad",
        ),
        (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36",
            "Chrome on Linux",
        ),
        ("curl/8.5.0", "Unknown browser"),
        ("SomeKit Chrome/126.0", "Chrome"),  # a browser but no system we know
        ("Mozilla/5.0 (X11; CrOS x86_64 14541.0.0) Firefox/127.0", "Firefox on ChromeOS"),
        ("", "Unknown device"),
        (None, "Unknown device"),
    ],
)
def test_a_user_agent_becomes_a_short_device_label(agent, label):
    assert rules.device_label(agent) == label
