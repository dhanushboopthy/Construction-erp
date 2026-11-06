"""Plans and limits for companies on the Duolink service (Milestone 16)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.plans import (
    TRIAL_DAYS,
    PlanLimits,
    TrialState,
    can_add,
    limits_for,
    trial_end,
    trial_state,
)

NOW = datetime(2026, 10, 24, 9, 0, tzinfo=UTC)
BASIC = PlanLimits(max_users=10, max_locations=3)


def test_plan_limits_apply_unless_the_company_has_its_own():
    assert limits_for(BASIC, None, None) == BASIC
    own = limits_for(BASIC, 25, None)
    assert own.max_users == 25 and own.max_locations == BASIC.max_locations
    assert limits_for(BASIC, None, 1).max_locations == 1


def test_a_lowered_plan_limit_is_what_a_company_without_its_own_gets():
    lowered = PlanLimits(max_users=2, max_locations=3)
    assert limits_for(lowered, None, None).max_users == 2
    assert limits_for(lowered, 8, None).max_users == 8  # a company's own limit still wins


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
