"""Plans and limits for companies on the Duolink service (Milestones 16 and 20, ADR 0012).

Pure rules: what a plan allows, a company's own overrides, where a trial stands, and the rules
for the plan catalogue Duolink edits (codes, prices, features, copies, deletion). The plans
themselves are rows in `platform_plan`; the service reads them and passes the values in. An
ended trial is only flagged for the Duolink admin; it never locks a company out of its books.
"""

import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from app.domain.plan_features import unknown_features

TRIAL_DAYS = 14
MAX_TRIAL_DAYS = 90
ENDING_SOON_DAYS = 7
TRIAL_PLAN_CODE = "TRIAL"  # the plan a new company starts on; its limits are edited like any
MAX_PRICES = 6
PLAN_CODE_MAX = 30
DURATION_UNITS = {"day": 3650, "month": 120, "year": 10}  # unit -> the longest duration
MAX_PRICE = Decimal("9999999999.99")  # NUMERIC(12,2)
_CODE = re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$")


@dataclass(frozen=True)
class PlanLimits:
    max_users: int  # active users
    max_locations: int  # active shops and godowns


class TrialState(StrEnum):
    NONE = "none"  # not on a trial
    RUNNING = "running"
    ENDING = "ending"  # ends within ENDING_SOON_DAYS
    ENDED = "ended"


def limits_for(base: PlanLimits, max_users: int | None, max_locations: int | None) -> PlanLimits:
    """The plan's limits, with the company's own limit where Duolink set one."""
    limits = base
    if max_users is not None:
        limits = replace(limits, max_users=max_users)
    if max_locations is not None:
        limits = replace(limits, max_locations=max_locations)
    return limits


class PlanRuleError(ValueError):
    """The plan catalogue refuses this. `code` is the API error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PriceTerms:
    duration_value: int
    duration_unit: str
    price: Decimal


def is_trial_plan(code: str) -> bool:
    return code == TRIAL_PLAN_CODE


def check_plan_code(typed: str) -> str:
    """Upper snake case, 2 to 30 characters. Spaces and hyphens become underscores."""
    code = re.sub(r"[\s-]+", "_", typed.strip().upper())
    if not 2 <= len(code) <= PLAN_CODE_MAX or not _CODE.match(code):
        raise PlanRuleError(
            "PLAN_CODE_INVALID",
            "A plan code is 2 to 30 capital letters, digits and single underscores, "
            "starting with a letter.",
        )
    return code


def check_limits(max_users: int, max_locations: int) -> None:
    if max_users < 1 or max_locations < 1:
        raise PlanRuleError("PLAN_LIMIT_INVALID", "A plan allows at least 1 user and 1 location.")


def check_features(codes: list[str]) -> list[str]:
    """Each feature once, in the order given; every one must be in the catalogue."""
    unknown = unknown_features(codes)
    if unknown:
        raise PlanRuleError("PLAN_FEATURE_UNKNOWN", f"Not a feature: {', '.join(unknown)}.")
    return list(dict.fromkeys(codes))


def _check_price(term: PriceTerms) -> None:
    longest = DURATION_UNITS.get(term.duration_unit)
    if longest is None or not 1 <= term.duration_value <= longest:
        raise PlanRuleError(
            "PLAN_PRICE_DURATION", "A price lasts a whole number of days, months or years."
        )
    amount = term.price
    if (
        not isinstance(amount, Decimal)
        or not amount.is_finite()
        or amount != amount.quantize(Decimal("0.01"))
        or not 0 <= amount <= MAX_PRICE
    ):
        raise PlanRuleError(
            "PLAN_PRICE_AMOUNT", "A price is not negative and has at most two decimals."
        )


def check_prices(prices: list[PriceTerms]) -> None:
    """One to six prices, each with its own duration."""
    if not 1 <= len(prices) <= MAX_PRICES:
        raise PlanRuleError("PLAN_PRICE_COUNT", f"A plan has 1 to {MAX_PRICES} prices.")
    for term in prices:
        _check_price(term)
    if len({(p.duration_value, p.duration_unit) for p in prices}) != len(prices):
        raise PlanRuleError("PLAN_PRICE_DUPLICATE", "Two prices have the same duration.")


def copy_code(code: str, taken: set[str]) -> str:
    """The first free code for a copy: PRO_COPY, PRO_COPY_2, PRO_COPY_3 ..."""
    n = 1
    while True:
        suffix = "_COPY" if n == 1 else f"_COPY_{n}"
        candidate = code[: PLAN_CODE_MAX - len(suffix)].rstrip("_") + suffix
        if candidate not in taken:
            return candidate
        n += 1


def check_deletable(companies_using: int) -> None:
    if companies_using > 0:
        raise PlanRuleError(
            "PLAN_IN_USE", "Companies are on this plan. Archive it instead of deleting it."
        )


def check_assignable(is_active: bool) -> None:
    if not is_active:
        raise PlanRuleError("PLAN_INACTIVE", "That plan is archived and cannot be given out.")


def can_add(current: int, limit: int) -> bool:
    """May one more be added when `current` are already in use?"""
    return current < limit


def trial_end(start: datetime, days: int = TRIAL_DAYS) -> datetime:
    return start + timedelta(days=days)


class OnboardingError(ValueError):
    """The onboarding form contradicts itself. `code` is the API error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def onboarding_terms(
    plan: str, *, start_active: bool, trial_days: int | None, now: datetime
) -> tuple[str, datetime | None]:
    """The new company's status and trial end. A trial-plan company is on trial for the chosen
    number of days (14 if blank), or starts active when Duolink says so. A paid plan starts
    active and has no trial."""
    if not is_trial_plan(plan):
        if trial_days is not None:
            raise OnboardingError(
                "TRIAL_ON_PAID_PLAN", "A paid plan starts active. Leave the trial length blank."
            )
        return "active", None
    if start_active:
        if trial_days is not None:
            raise OnboardingError(
                "TRIAL_CONFLICT", "Choose either a trial length or start active, not both."
            )
        return "active", None
    days = TRIAL_DAYS if trial_days is None else trial_days
    if not 1 <= days <= MAX_TRIAL_DAYS:
        raise OnboardingError("TRIAL_DAYS", f"A trial lasts 1 to {MAX_TRIAL_DAYS} days.")
    return "trial", trial_end(now, days)


def trial_state(ends_at: datetime | None, now: datetime) -> TrialState:
    if ends_at is None:
        return TrialState.NONE
    if ends_at <= now:
        return TrialState.ENDED
    if ends_at - now <= timedelta(days=ENDING_SOON_DAYS):
        return TrialState.ENDING
    return TrialState.RUNNING
