"""Milestone 12: cash drawer, pro rata splits and financial-year months, with worked numbers."""

from datetime import date
from decimal import Decimal as D

import pytest

from app.domain import closing
from app.domain.fiscal import fy_months
from app.domain.money import split_pro_rata


def test_expected_cash_is_opening_plus_in_less_out():
    # Opening ₹5,000; cash taken ₹42,350.50; cash paid out ₹3,000 -> ₹44,350.50 should be there.
    assert closing.expected_cash(D("5000"), D("42350.50"), D("3000")) == D("44350.50")


def test_difference_is_counted_less_expected():
    assert closing.cash_difference(D("44350.50"), D("44350.50")) == D("0.00")
    assert closing.cash_difference(D("44300"), D("44350.50")) == D("-50.50")  # short
    assert closing.cash_difference(D("44400"), D("44350.50")) == D("49.50")  # over


def test_a_difference_needs_a_note_and_a_count_cannot_be_negative():
    assert closing.note_needed(D("-0.01")) and closing.note_needed(D("5"))
    assert not closing.note_needed(D("0.00"))
    with pytest.raises(ValueError, match="negative"):
        closing.cash_difference(D("-1"), D("10"))


def test_split_pro_rata_adds_up_exactly():
    # ₹3,000 freight over two lines of ₹1,12,000 and ₹56,000 is 2,000 and 1,000.
    assert split_pro_rata(D("3000"), [D("112000"), D("56000")]) == [D("2000.00"), D("1000.00")]
    # ₹100 over three equal lines: the odd paisa goes to the first of the tied shares.
    parts = split_pro_rata(D("100"), [D("1"), D("1"), D("1")])
    assert parts == [D("33.34"), D("33.33"), D("33.33")] and sum(parts) == D("100.00")
    # The largest remainder gets the extra paisa: 0.10 over 1:2 -> 0.03 and 0.07 (3.33 vs 6.67).
    assert split_pro_rata(D("0.10"), [D("1"), D("2")]) == [D("0.03"), D("0.07")]
    assert split_pro_rata(D("0"), [D("1"), D("2")]) == [D("0.00"), D("0.00")]
    assert split_pro_rata(D("-100"), [D("1"), D("3")]) == [D("-25.00"), D("-75.00")]
    # A negative total with odd paise still adds up: -0.10 over 1:2 is -0.03 and -0.07.
    assert split_pro_rata(D("-0.10"), [D("1"), D("2")]) == [D("-0.03"), D("-0.07")]


def test_split_pro_rata_needs_weights():
    with pytest.raises(ValueError, match="weights"):
        split_pro_rata(D("10"), [])
    with pytest.raises(ValueError, match="weights"):
        split_pro_rata(D("10"), [D("0"), D("0")])
    with pytest.raises(ValueError, match="weights"):
        split_pro_rata(D("10"), [D("-1"), D("2")])


def test_months_of_a_financial_year():
    months = fy_months(2026, 4)
    assert months[0] == (2026, 4) and months[8] == (2026, 12) and months[9] == (2027, 1)
    assert months[-1] == (2027, 3) and len(months) == 12
    assert fy_months(2026, 1)[0] == (2026, 1) and fy_months(2026, 1)[-1] == (2026, 12)


def test_month_label():
    assert closing.month_key(date(2026, 4, 30)) == "2026-04"
