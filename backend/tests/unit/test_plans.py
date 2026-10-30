"""Plans and limits for companies on the Duolink service (Milestone 16)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.plans import (
    PLANS,
    TRIAL_DAYS,
    TrialState,
    can_add,
    limits_for,
    trial_end,
    trial_state,
)

NOW = datetime(2026, 10, 24, 9, 0, tzinfo=UTC)


def test_every_plan_has_limits_and_bigger_plans_allow_more():
    assert set(PLANS) == {"trial", "basic", "pro"}
    assert PLANS["trial"].max_users <= PLANS["basic"].max_users <= PLANS["pro"].max_users
    assert (
        PLANS["trial"].max_locations <= PLANS["basic"].max_locations <= PLANS["pro"].max_locations
    )


def test_plan_limits_apply_unless_the_company_has_its_own():
    assert limits_for("basic", None, None) == PLANS["basic"]
    own = limits_for("basic", 25, None)
    assert own.max_users == 25 and own.max_locations == PLANS["basic"].max_locations
    assert limits_for("pro", None, 1).max_locations == 1


def test_unknown_plan_is_refused():
    with pytest.raises(ValueError, match="plan"):
        limits_for("gold", None, None)


@pytest.mark.parametrize(
    ("current", "limit", "allowed"),
    [(0, 5, True), (4, 5, True), (5, 5, False), (7, 5, False), (0, 0, False)],
)
def test_can_add_one_more_only_below_the_limit(current, limit, allowed):
    assert can_add(current, limit) is allowed


def test_a_trial_lasts_fourteen_days():
    assert TRIAL_DAYS == 14
    assert trial_end(NOW) == NOW + timedelta(days=14)


@pytest.mark.parametrize(
    ("ends", "state"),
    [
        (None, TrialState.NONE),
        (NOW + timedelta(days=8), TrialState.RUNNING),
        (NOW + timedelta(days=7), TrialState.ENDING),
        (NOW + timedelta(hours=1), TrialState.ENDING),
        (NOW, TrialState.ENDED),
        (NOW - timedelta(days=3), TrialState.ENDED),
    ],
)
def test_trial_state(ends, state):
    assert trial_state(ends, NOW) is state
