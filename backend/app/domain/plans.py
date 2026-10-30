"""Plans and limits for companies on the Duolink service (Milestone 16, ADR 0012).

Pure rules: what each plan allows, a company's own overrides, and where a trial stands. An
ended trial is only flagged for the Duolink admin; it never locks a company out of its books.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum

TRIAL_DAYS = 14
ENDING_SOON_DAYS = 7


@dataclass(frozen=True)
class PlanLimits:
    max_users: int  # active users
    max_locations: int  # active shops and godowns


# Editable: what Duolink sells. Keys match TenantPlan values.
PLANS: dict[str, PlanLimits] = {
    "trial": PlanLimits(max_users=5, max_locations=2),
    "basic": PlanLimits(max_users=10, max_locations=3),
    "pro": PlanLimits(max_users=50, max_locations=10),
}


class TrialState(StrEnum):
    NONE = "none"  # not on a trial
    RUNNING = "running"
    ENDING = "ending"  # ends within ENDING_SOON_DAYS
    ENDED = "ended"


def limits_for(plan: str, max_users: int | None, max_locations: int | None) -> PlanLimits:
    """The plan's limits, with the company's own limit where Duolink set one."""
    if plan not in PLANS:
        raise ValueError(f"Unknown plan {plan!r}")
    limits = PLANS[plan]
    if max_users is not None:
        limits = replace(limits, max_users=max_users)
    if max_locations is not None:
        limits = replace(limits, max_locations=max_locations)
    return limits


def can_add(current: int, limit: int) -> bool:
    """May one more be added when `current` are already in use?"""
    return current < limit


def trial_end(start: datetime) -> datetime:
    return start + timedelta(days=TRIAL_DAYS)


def trial_state(ends_at: datetime | None, now: datetime) -> TrialState:
    if ends_at is None:
        return TrialState.NONE
    if ends_at <= now:
        return TrialState.ENDED
    if ends_at - now <= timedelta(days=ENDING_SOON_DAYS):
        return TrialState.ENDING
    return TrialState.RUNNING
