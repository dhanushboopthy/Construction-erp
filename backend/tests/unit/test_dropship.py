"""Milestone 8-9 rules for direct (drop-ship) sales and freight, with hand-worked numbers."""

from decimal import Decimal as D

import pytest

from app.domain import dropship
from app.domain.compliance import freight_cash_warning


def test_profit_is_sale_less_purchase_less_freight():
    # Sold 1,000 kg for ₹60,000 taxable; the supplier's landed cost is ₹52.50/kg = ₹52,500;
    # freight to the site ₹3,000. Profit 60,000 - 52,500 - 3,000 = 4,500.
    assert dropship.profit(D("60000"), D("1000"), D("52.5"), D("3000")) == D("4500.00")


def test_profit_can_be_a_loss_and_rounds_to_paise():
    # 3 bags at ₹100.004 cost = 300.012 -> 300.01; sale 300.00; no freight: -0.01.
    assert dropship.profit(D("300"), D("3"), D("100.004"), D("0")) == D("-0.01")


def test_remaining_to_link_and_over_link():
    # A purchase line of 5,000 kg with 3,200 kg already tied to sales leaves 1,800 kg.
    assert dropship.remaining_to_link(D("5000"), [D("2000"), D("1200")]) == D("1800.000")
    dropship.check_link(D("5000"), [D("3200")], D("1800"))  # exactly what is left is fine
    with pytest.raises(ValueError, match="only 1800 kg"):
        dropship.check_link(D("5000"), [D("3200")], D("1800.001"), unit="kg")
    with pytest.raises(ValueError, match="positive"):
        dropship.check_link(D("5000"), [], D("0"))


def test_cash_freight_over_the_daily_limit_gets_a_warning():
    # ₹35,000 a day in cash to one transporter is the limit for the deduction (G14).
    assert not freight_cash_warning(D("20000"), D("15000"), D("35000"))  # exactly the limit
    assert freight_cash_warning(D("20000"), D("15000.01"), D("35000"))
    assert not freight_cash_warning(D("0"), D("0"), D("35000"))
