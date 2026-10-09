"""Milestone 11: supplier target schemes (rule B15) with hand-worked numbers."""

from datetime import date
from decimal import Decimal as D

import pytest

from app.domain import schemes


def test_progress_and_the_80_percent_alert():
    # Target 1,00,000 kg; bought 82,500 kg: 82.50%, 17,500 kg to go, alert on.
    p = schemes.progress(D("100000"), D("82500"))
    assert (p.pct, p.remaining, p.reached, p.alert) == (D("82.50"), D("17500.000"), False, True)


def test_alert_starts_exactly_at_80_percent_and_stops_at_the_target():
    just_under = schemes.progress(D("100000"), D("79999.999"))
    assert (
        just_under.pct == D("80.00") and just_under.alert is False
    )  # shown 80.00 but not yet there
    assert schemes.progress(D("100000"), D("80000")).alert is True
    done = schemes.progress(D("100000"), D("100000"))
    assert (done.reached, done.alert, done.remaining) == (True, False, D("0.000"))
    over = schemes.progress(D("100000"), D("120000"))
    assert (over.pct, over.remaining, over.reached) == (D("120.00"), D("0.000"), True)


def test_progress_needs_a_positive_target_and_no_negative_volume():
    with pytest.raises(ValueError, match="target"):
        schemes.progress(D("0"), D("10"))
    with pytest.raises(ValueError, match="negative"):
        schemes.progress(D("100"), D("-1"))


def test_rebate_rules():
    # 2% of ₹5,50,000 of qualifying purchases = ₹11,000.
    assert schemes.rebate_amount(schemes.RebateRule.PERCENT, D("2"), D("550000"), D("100000")) == D(
        "11000.00"
    )
    # ₹0.50 a kg on 1,00,000 kg = ₹50,000.
    assert schemes.rebate_amount(
        schemes.RebateRule.PER_UNIT, D("0.5"), D("550000"), D("100000")
    ) == D("50000.00")
    # A flat ₹25,000 whatever was bought.
    assert schemes.rebate_amount(schemes.RebateRule.FLAT, D("25000"), D("1"), D("1")) == D(
        "25000.00"
    )
    # Paise are rounded half up: 1.5% of ₹333.33 = 4.99995 -> 5.00.
    assert schemes.rebate_amount(schemes.RebateRule.PERCENT, D("1.5"), D("333.33"), D("10")) == D(
        "5.00"
    )


def test_rebate_cannot_be_negative():
    with pytest.raises(ValueError, match="negative"):
        schemes.rebate_amount(schemes.RebateRule.FLAT, D("-1"), D("1"), D("1"))


def test_a_purchase_counts_when_it_falls_in_the_period():
    start, end = date(2026, 4, 1), date(2026, 9, 30)
    assert schemes.in_period(date(2026, 4, 1), start, end)
    assert schemes.in_period(date(2026, 9, 30), start, end)
    assert not schemes.in_period(date(2026, 3, 31), start, end)
    assert not schemes.in_period(date(2026, 10, 1), start, end)
