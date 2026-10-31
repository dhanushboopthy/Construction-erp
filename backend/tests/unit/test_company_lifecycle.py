"""Company identity numbers, status changes and onboarding terms (Milestone 18)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.gst import is_valid_cin, is_valid_pan, pan_of
from app.domain.plans import MAX_TRIAL_DAYS, TRIAL_DAYS, OnboardingError, onboarding_terms
from app.domain.tenancy import StatusChangeError, status_after

NOW = datetime(2026, 10, 31, 9, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("pan", "ok"),
    [
        ("AAPFU0939F", True),  # 5 letters, 4 digits, 1 letter
        ("aapfu0939f", True),  # case does not matter
        ("AAPFU0939", False),
        ("AAPF10939F", False),  # the fifth character is a letter
        ("1APFU0939F", False),
        ("", False),
    ],
)
def test_pan_is_five_letters_four_digits_and_a_letter(pan, ok):
    assert is_valid_pan(pan) is ok


@pytest.mark.parametrize(
    ("cin", "ok"),
    [
        ("U45200TN2015PTC098765", True),  # listed/unlisted, 5 digits, state, year, type, 6 digits
        ("L17110MH1973PLC019786", True),
        ("u45200tn2015ptc098765", True),
        ("X45200TN2015PTC098765", False),  # must begin with L or U
        ("U45200TN2015PTC09876", False),  # one digit short
        ("U4520TN2015PTC0987655", False),
        ("", False),
    ],
)
def test_cin_is_twenty_one_characters_in_the_registrars_layout(cin, ok):
    assert is_valid_cin(cin) is ok


def test_a_pan_inside_a_gstin_is_found_by_pan_of():
    # 27 AAPFU0939F 1 Z V: characters 3 to 12 are the PAN, and they pass the PAN check.
    assert is_valid_pan(pan_of("27AAPFU0939F1ZV") or "")


@pytest.mark.parametrize(
    ("current", "action", "on_trial", "result"),
    [
        ("trial", "suspend", True, "suspended"),
        ("active", "suspend", False, "suspended"),
        ("trial", "cancel", True, "cancelled"),
        ("active", "cancel", False, "cancelled"),
        ("suspended", "cancel", False, "cancelled"),
        ("suspended", "reactivate", True, "trial"),  # a trial-plan company goes back on trial
        ("suspended", "reactivate", False, "active"),
        ("cancelled", "reactivate", True, "trial"),
        ("cancelled", "reactivate", False, "active"),
    ],
)
def test_status_changes_that_are_allowed(current, action, on_trial, result):
    assert status_after(current, action, on_trial_plan=on_trial) == result


@pytest.mark.parametrize(
    ("current", "action", "code"),
    [
        ("suspended", "suspend", "ALREADY_SUSPENDED"),
        ("cancelled", "suspend", "ALREADY_CANCELLED"),  # a closed company is not suspended
        ("cancelled", "cancel", "ALREADY_CANCELLED"),
        ("active", "reactivate", "NOT_SUSPENDED"),
        ("trial", "reactivate", "NOT_SUSPENDED"),
    ],
)
def test_status_changes_that_are_refused(current, action, code):
    with pytest.raises(StatusChangeError) as caught:
        status_after(current, action, on_trial_plan=False)
    assert caught.value.code == code


def test_an_unknown_status_action_is_a_programming_error():
    with pytest.raises(ValueError, match="action"):
        status_after("active", "delete", on_trial_plan=False)


def test_a_trial_plan_company_starts_on_a_trial_of_the_chosen_length():
    # 31 Oct 2026 09:00 + 30 days = 30 Nov 2026 09:00; the default is 14 days.
    status, ends = onboarding_terms("trial", start_active=False, trial_days=30, now=NOW)
    assert (status, ends) == ("trial", NOW + timedelta(days=30))
    status, ends = onboarding_terms("trial", start_active=False, trial_days=None, now=NOW)
    assert ends == NOW + timedelta(days=TRIAL_DAYS)


def test_start_active_skips_the_trial():
    assert onboarding_terms("trial", start_active=True, trial_days=None, now=NOW) == (
        "active",
        None,
    )


def test_a_paid_plan_starts_active_with_no_trial():
    assert onboarding_terms("basic", start_active=False, trial_days=None, now=NOW) == (
        "active",
        None,
    )
    assert onboarding_terms("pro", start_active=True, trial_days=None, now=NOW) == ("active", None)


@pytest.mark.parametrize(
    ("plan", "start_active", "days", "code"),
    [
        ("trial", True, 10, "TRIAL_CONFLICT"),  # "start active" and a trial length together
        ("basic", False, 10, "TRIAL_ON_PAID_PLAN"),
        ("trial", False, 0, "TRIAL_DAYS"),
        ("trial", False, MAX_TRIAL_DAYS + 1, "TRIAL_DAYS"),
    ],
)
def test_onboarding_terms_that_contradict_themselves_are_refused(plan, start_active, days, code):
    with pytest.raises(OnboardingError) as caught:
        onboarding_terms(plan, start_active=start_active, trial_days=days, now=NOW)
    assert caught.value.code == code
