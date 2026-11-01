"""Subscriptions: renewal periods, access state, days left and payment rules (Milestone 21).

Every date is written out so the rule can be checked by eye.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.domain.subscriptions import (
    AccessState,
    SubscriptionRuleError,
    access_state,
    add_duration,
    add_months,
    check_cancellable,
    check_payment,
    check_reversible,
    days_left,
    effective_status,
    expiring_within,
    month_start,
    renewal_period,
    reversal_of,
    twelve_months_ending,
)


def at(y: int, m: int, d: int, h: int = 9) -> datetime:
    return datetime(y, m, d, h, 0, tzinfo=UTC)


# ---------------------------------------------------------------- month arithmetic


def test_adding_a_month_clamps_the_day():
    # 31 Jan 2026 + 1 month: February 2026 has 28 days.
    assert add_months(at(2026, 1, 31), 1) == at(2026, 2, 28)
    # 31 Jan 2028 + 1 month: 2028 is a leap year.
    assert add_months(at(2028, 1, 31), 1) == at(2028, 2, 29)
    # 30 Nov 2026 + 3 months lands on 28 Feb 2027.
    assert add_months(at(2026, 11, 30), 3) == at(2027, 2, 28)


def test_adding_months_crosses_the_year():
    assert add_months(at(2026, 12, 15), 1) == at(2027, 1, 15)
    assert add_months(at(2026, 10, 1), 14) == at(2027, 12, 1)


def test_a_year_from_a_leap_day_clamps():
    # 29 Feb 2028 + 1 year -> 28 Feb 2029.
    assert add_duration(at(2028, 2, 29), 1, "year") == at(2029, 2, 28)


def test_days_months_years():
    assert add_duration(at(2026, 10, 31), 14, "day") == at(2026, 11, 14)
    assert add_duration(at(2026, 10, 31), 1, "month") == at(2026, 11, 30)
    assert add_duration(at(2026, 11, 12), 1, "year") == at(2027, 11, 12)


def test_an_unknown_unit_is_refused():
    with pytest.raises(ValueError, match="Unknown duration unit"):
        add_duration(at(2026, 1, 1), 1, "week")


# ---------------------------------------------------------------- renewal periods


def test_paying_during_a_trial_starts_the_paid_period_today():
    # Trial ends 20 Nov; paid on 5 Nov for 1 month: 5 Nov to 5 Dec. The unused trial days
    # are not carried over.
    period = renewal_period(
        status="trial",
        expires_at=at(2026, 11, 20),
        duration_value=1,
        duration_unit="month",
        now=at(2026, 11, 5),
    )
    assert period.starts_at == at(2026, 11, 5)
    assert period.expires_at == at(2026, 12, 5)


def test_renewing_early_adds_the_time_on_top_of_the_current_expiry():
    # Paid until 12 Nov; renewed on 1 Nov for 1 year: 12 Nov 2026 to 12 Nov 2027.
    period = renewal_period(
        status="active",
        expires_at=at(2026, 11, 12),
        duration_value=1,
        duration_unit="year",
        now=at(2026, 11, 1),
    )
    assert period.starts_at == at(2026, 11, 12)
    assert period.expires_at == at(2027, 11, 12)


def test_renewing_after_expiry_starts_today():
    # Expired 12 Oct; renewed on 20 Nov for 3 months: 20 Nov to 20 Feb.
    period = renewal_period(
        status="active",
        expires_at=at(2026, 10, 12),
        duration_value=3,
        duration_unit="month",
        now=at(2026, 11, 20),
    )
    assert period.starts_at == at(2026, 11, 20)
    assert period.expires_at == at(2027, 2, 20)


def test_renewing_a_cancelled_subscription_starts_today():
    period = renewal_period(
        status="cancelled",
        expires_at=at(2027, 1, 1),
        duration_value=30,
        duration_unit="day",
        now=at(2026, 11, 20),
    )
    assert period.starts_at == at(2026, 11, 20)
    assert period.expires_at == at(2026, 12, 20)


def test_a_renewal_that_clamps_the_month_end():
    # Paid until 31 Jan 2027, renewed early for 1 month: 28 Feb 2027.
    period = renewal_period(
        status="active",
        expires_at=at(2027, 1, 31),
        duration_value=1,
        duration_unit="month",
        now=at(2027, 1, 10),
    )
    assert period.expires_at == at(2027, 2, 28)


def test_a_renewal_without_an_expiry_starts_today():
    period = renewal_period(
        status="active",
        expires_at=None,
        duration_value=14,
        duration_unit="day",
        now=at(2026, 11, 20),
    )
    assert period.starts_at == at(2026, 11, 20)
    assert period.expires_at == at(2026, 12, 4)


def test_a_renewal_needs_a_positive_duration():
    for value in (0, -1):
        with pytest.raises(SubscriptionRuleError) as err:
            renewal_period(
                status="active",
                expires_at=None,
                duration_value=value,
                duration_unit="day",
                now=at(2026, 11, 20),
            )
        assert err.value.code == "RENEWAL_DURATION"


def test_a_renewal_cannot_run_past_ten_years():
    with pytest.raises(SubscriptionRuleError) as err:
        renewal_period(
            status="active",
            expires_at=None,
            duration_value=11,
            duration_unit="year",
            now=at(2026, 11, 20),
        )
    assert err.value.code == "RENEWAL_DURATION"
    with pytest.raises(SubscriptionRuleError):
        renewal_period(
            status="active",
            expires_at=None,
            duration_value=3651,
            duration_unit="day",
            now=at(2026, 11, 20),
        )


# ---------------------------------------------------------------- status and access


def test_effective_status_follows_the_date():
    now = at(2026, 11, 12)
    assert effective_status("active", at(2026, 11, 13), now) == "active"
    assert effective_status("active", at(2026, 11, 12), now) == "expired"  # ends this instant
    assert effective_status("active", at(2026, 11, 1), now) == "expired"
    assert effective_status("trial", at(2026, 11, 13), now) == "trial"
    assert effective_status("trial", at(2026, 11, 1), now) == "expired"
    assert effective_status("cancelled", at(2027, 1, 1), now) == "cancelled"
    assert effective_status("active", None, now) == "active"


def test_access_is_full_while_the_subscription_runs():
    state = access_state(
        company_status="active",
        subscription_status="active",
        expires_at=at(2026, 12, 1),
        now=at(2026, 11, 12),
    )
    assert state is AccessState.FULL


def test_an_expired_subscription_is_read_only():
    state = access_state(
        company_status="active",
        subscription_status="active",
        expires_at=at(2026, 11, 1),
        now=at(2026, 11, 12),
    )
    assert state is AccessState.READ_ONLY


def test_an_ended_trial_with_no_payment_is_read_only():
    state = access_state(
        company_status="trial",
        subscription_status="trial",
        expires_at=at(2026, 11, 1),
        now=at(2026, 11, 12),
    )
    assert state is AccessState.READ_ONLY


def test_a_running_trial_has_full_access():
    state = access_state(
        company_status="trial",
        subscription_status="trial",
        expires_at=at(2026, 11, 20),
        now=at(2026, 11, 12),
    )
    assert state is AccessState.FULL


def test_a_cancelled_subscription_is_read_only():
    state = access_state(
        company_status="active",
        subscription_status="cancelled",
        expires_at=at(2027, 1, 1),
        now=at(2026, 11, 12),
    )
    assert state is AccessState.READ_ONLY


@pytest.mark.parametrize("company_status", ["suspended", "cancelled"])
def test_a_suspended_or_closed_company_is_blocked_whatever_the_dates(company_status):
    state = access_state(
        company_status=company_status,
        subscription_status="active",
        expires_at=at(2027, 1, 1),
        now=at(2026, 11, 12),
    )
    assert state is AccessState.BLOCKED


def test_a_company_without_a_subscription_date_is_not_locked():
    state = access_state(
        company_status="active", subscription_status="active", expires_at=None, now=at(2026, 11, 12)
    )
    assert state is AccessState.FULL


# ---------------------------------------------------------------- days left


def test_days_left_counts_whole_days_rounding_up():
    now = at(2026, 11, 12, 9)
    assert days_left(at(2026, 11, 19, 9), now) == 7
    assert days_left(at(2026, 11, 19, 8), now) == 7  # 6 days 23 hours: still "7 days"
    assert days_left(at(2026, 11, 12, 10), now) == 1
    assert days_left(at(2026, 11, 12, 9), now) == 0
    assert days_left(at(2026, 11, 10, 9), now) == -2
    assert days_left(None, now) is None


def test_expiring_within_includes_the_boundary_and_excludes_the_expired():
    now = at(2026, 11, 12, 9)
    assert expiring_within(at(2026, 12, 12, 9), now, 30)  # exactly 30 days
    assert not expiring_within(at(2026, 12, 12, 10), now, 30)  # 31 days
    assert expiring_within(at(2026, 11, 12, 10), now, 30)
    assert not expiring_within(at(2026, 11, 12, 9), now, 30)  # already ended
    assert not expiring_within(at(2026, 11, 1), now, 30)
    assert not expiring_within(None, now, 30)


# ---------------------------------------------------------------- payments


def test_a_payment_amount_has_two_decimals_and_is_not_negative():
    check_payment(Decimal("999.90"), "upi")
    check_payment(Decimal("0.00"), "cash")  # a complimentary extension is still recorded
    for bad in (Decimal("-1.00"), Decimal("10.001"), Decimal("NaN"), Decimal("Infinity")):
        with pytest.raises(SubscriptionRuleError) as err:
            check_payment(bad, "cash")
        assert err.value.code == "PAYMENT_AMOUNT"
    with pytest.raises(SubscriptionRuleError):
        check_payment(Decimal("10000000000.00"), "cash")


def test_a_payment_method_must_be_known():
    for method in ("cash", "bank", "upi", "cheque", "razorpay"):
        check_payment(Decimal("1.00"), method)
    with pytest.raises(SubscriptionRuleError) as err:
        check_payment(Decimal("1.00"), "bitcoin")
    assert err.value.code == "PAYMENT_METHOD"


def test_a_reversal_is_the_same_amount_negated():
    assert reversal_of(Decimal("999.90")) == Decimal("-999.90")
    assert reversal_of(Decimal("0.00")) == Decimal("0.00")


def test_a_payment_can_be_reversed_once():
    check_reversible(Decimal("500.00"), already_reversed=False)
    with pytest.raises(SubscriptionRuleError) as err:
        check_reversible(Decimal("500.00"), already_reversed=True)
    assert err.value.code == "PAYMENT_REVERSED"


def test_a_reversal_cannot_be_reversed():
    with pytest.raises(SubscriptionRuleError) as err:
        check_reversible(Decimal("-500.00"), already_reversed=False)
    assert err.value.code == "PAYMENT_IS_REVERSAL"


def test_cancelling_twice_is_refused():
    check_cancellable("active")
    check_cancellable("trial")
    with pytest.raises(SubscriptionRuleError) as err:
        check_cancellable("cancelled")
    assert err.value.code == "ALREADY_CANCELLED"


# ---------------------------------------------------------------- reporting windows


def test_month_start():
    assert month_start(date(2026, 11, 12)) == date(2026, 11, 1)
    assert month_start(date(2026, 1, 31)) == date(2026, 1, 1)


def test_twelve_months_ending_this_month_is_oldest_first():
    months = twelve_months_ending(date(2026, 11, 12))
    assert len(months) == 12
    assert months[0] == date(2025, 12, 1)
    assert months[-1] == date(2026, 11, 1)
    assert twelve_months_ending(date(2026, 2, 28))[0] == date(2025, 3, 1)
