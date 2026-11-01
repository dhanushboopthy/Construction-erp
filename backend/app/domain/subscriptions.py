"""Subscriptions: when a paid period starts and ends, what a lapsed company may do, and the rules
for Duolink's payment records (Milestone 21, ADR 0013).

Pure rules: no database, no clock (pass `now` in). A subscription is stored with a status of
`trial`, `active` or `cancelled`; whether it has run out is worked out from `expires_at`, so
nothing has to run at midnight and a renewal takes effect on the next request.
"""

import calendar
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from app.domain.plans import DURATION_UNITS, MAX_PRICE

PAYMENT_METHODS = ("cash", "bank", "upi", "cheque", "razorpay")
BANNER_DAYS = 7  # the company is told its plan is ending from this many days before


class AccessState(StrEnum):
    FULL = "full"
    READ_ONLY = "read_only"  # the books can be read and exported, nothing can be written
    BLOCKED = "blocked"  # suspended or closed company: nobody gets in (unchanged, M16)


class SubscriptionRuleError(ValueError):
    """Duolink's billing rules refuse this. `code` is the API error code (409)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Period:
    starts_at: datetime
    expires_at: datetime


def add_months(start: datetime, months: int) -> datetime:
    """`months` later, keeping the time. The day is clamped to the month's length, so
    31 Jan + 1 month is 28 Feb (29 in a leap year)."""
    index = start.year * 12 + (start.month - 1) + months
    year, month = divmod(index, 12)
    month += 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return start.replace(year=year, month=month, day=day)


def add_duration(start: datetime, value: int, unit: str) -> datetime:
    if unit == "day":
        return start + timedelta(days=value)
    if unit == "month":
        return add_months(start, value)
    if unit == "year":
        return add_months(start, value * 12)
    raise ValueError(f"Unknown duration unit {unit!r}")


def renewal_period(
    *,
    status: str,
    expires_at: datetime | None,
    duration_value: int,
    duration_unit: str,
    now: datetime,
) -> Period:
    """The paid period a renewal buys.

    - Paying during a trial starts the paid period now; the unused trial is not carried over.
    - Renewing a paid subscription before it ends adds the time on top of the current expiry.
    - Renewing after it ended (or after a cancellation) starts now.
    """
    longest = DURATION_UNITS.get(duration_unit)
    if longest is None or not 1 <= duration_value <= longest:
        raise SubscriptionRuleError(
            "RENEWAL_DURATION", "A renewal lasts a whole number of days, months or years."
        )
    carries_on = status == "active" and expires_at is not None and expires_at > now
    starts_at = expires_at if carries_on and expires_at is not None else now
    return Period(starts_at, add_duration(starts_at, duration_value, duration_unit))


def effective_status(status: str, expires_at: datetime | None, now: datetime) -> str:
    """`trial`, `active`, `expired` or `cancelled`: the stored status, unless it has run out."""
    if status == "cancelled":
        return "cancelled"
    if expires_at is not None and expires_at <= now:
        return "expired"
    return status


def access_state(
    *,
    company_status: str,
    subscription_status: str,
    expires_at: datetime | None,
    now: datetime,
) -> AccessState:
    """What the company may do right now. A suspended or closed company is blocked outright. An
    ended subscription (a lapsed trial too) or a cancelled one makes the company read-only."""
    if company_status in {"suspended", "cancelled"}:
        return AccessState.BLOCKED
    if effective_status(subscription_status, expires_at, now) in {"expired", "cancelled"}:
        return AccessState.READ_ONLY
    return AccessState.FULL


def days_left(expires_at: datetime | None, now: datetime) -> int | None:
    """Whole days until the end, rounding part days up; negative once it has ended."""
    if expires_at is None:
        return None
    return math.ceil((expires_at - now) / timedelta(days=1))


def expiring_within(expires_at: datetime | None, now: datetime, days: int) -> bool:
    """Still running, and ending within `days` days."""
    if expires_at is None:
        return False
    return timedelta(0) < expires_at - now <= timedelta(days=days)


def check_payment(amount: Decimal, method: str) -> None:
    if (
        not isinstance(amount, Decimal)
        or not amount.is_finite()
        or amount != amount.quantize(Decimal("0.01"))
        or not 0 <= amount <= MAX_PRICE
    ):
        raise SubscriptionRuleError(
            "PAYMENT_AMOUNT", "An amount is not negative and has at most two decimals."
        )
    if method not in PAYMENT_METHODS:
        raise SubscriptionRuleError("PAYMENT_METHOD", "Choose how the money was received.")


def reversal_of(amount: Decimal) -> Decimal:
    """A mistaken payment is corrected by a row of the opposite sign, never edited."""
    return -amount if amount else Decimal("0.00")


def check_reversible(amount: Decimal, *, already_reversed: bool) -> None:
    if amount < 0:
        raise SubscriptionRuleError(
            "PAYMENT_IS_REVERSAL", "That row is itself a reversal. Record a new payment instead."
        )
    if already_reversed:
        raise SubscriptionRuleError("PAYMENT_REVERSED", "That payment was already reversed.")


def check_cancellable(status: str) -> None:
    if status == "cancelled":
        raise SubscriptionRuleError("ALREADY_CANCELLED", "That subscription is already cancelled.")


def month_start(on: date) -> date:
    return on.replace(day=1)


def twelve_months_ending(on: date) -> list[date]:
    """The first day of each of the 12 months up to and including `on`'s month, oldest first."""
    index = on.year * 12 + on.month - 1
    return [date((i // 12), (i % 12) + 1, 1) for i in range(index - 11, index + 1)]


__all__ = ["BANNER_DAYS", "MAX_PRICE", "PAYMENT_METHODS"]
