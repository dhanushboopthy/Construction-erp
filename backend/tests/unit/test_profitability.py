"""Profitability cuts (FM8, docs/FINANCE_REVIEW.md F19). Hand-worked numbers.

October, TMT sold by weight:
  Brand A: 10 t = 10,000 kg sold at ₹56/kg = ₹5,60,000; cost ₹55/kg = ₹5,50,000; freight ₹4,000
    gross profit = 5,60,000 - 5,50,000 - 4,000 = ₹6,000 -> ₹600 a ton, ₹0.60 a kg, 1.07 % margin
  Brand B: 4 t = 4,000 kg at ₹57/kg = ₹2,28,000; cost ₹55.50/kg = ₹2,22,000; no freight
    gross profit = ₹6,000 -> ₹1,500 a ton
  Both: 14 t; profit ₹12,000 -> ₹857.14 a ton
  Brand A's share of the profit = 6,000 ÷ 12,000 = 50 %

Contribution per ton for brand A with ₹1,000 loading labour and ₹500 of stock lost:
  (5,60,000 - 5,50,000 - 4,000 - 1,000 - 500) ÷ 10 t = ₹450 a ton

Units: 1,000 kg = 1 ton; a cement item sold in bags is counted in bags, never in tons.
"""

from decimal import Decimal

import pytest

from app.domain import finance as f

D = Decimal


def test_tons_from_kilograms() -> None:
    assert f.tons(D("10000")) == D("10.000")
    assert f.tons(D("4250")) == D("4.250")
    assert f.tons(D("0")) == D("0.000")


def test_profit_per_ton_for_each_brand_and_both() -> None:
    assert f.profit_per_unit(D("6000"), D("10")) == D("600.00")
    assert f.profit_per_unit(D("6000"), D("4")) == D("1500.00")
    assert f.profit_per_unit(D("12000"), D("14")) == D("857.14")
    assert f.profit_per_unit(D("-500"), D("2")) == D("-250.00")  # a loss is a negative number


def test_no_quantity_is_none_not_zero() -> None:
    assert f.profit_per_unit(D("6000"), D("0")) is None
    assert f.contribution_per_ton(D("100"), D("90"), D("0"), D("0"), D("0"), D("0")) is None


def test_margin_per_base_unit() -> None:
    # ₹6,000 over 10,000 kg is 60 paise a kilogram (4 decimals kept).
    assert f.margin_per_base_unit(D("6000"), D("10000")) == D("0.6000")
    assert f.margin_per_base_unit(D("6000"), D("0")) is None


def test_contribution_per_ton_is_after_loading_and_stock_lost() -> None:
    got = f.contribution_per_ton(
        net_sales=D("560000"),
        cogs=D("550000"),
        freight=D("4000"),
        variable_expenses=D("1000"),
        stock_lost=D("500"),
        tons_sold=D("10"),
    )
    assert got == D("450.00")


@pytest.mark.parametrize(
    ("part", "whole", "expected"),
    [
        ("6000", "12000", "50.00"),
        ("4000", "12000", "33.33"),
        ("100", "0", None),
        ("-100", "400", "-25.00"),
    ],
)
def test_share_of_the_total(part: str, whole: str, expected: str | None) -> None:
    want = None if expected is None else D(expected)
    assert f.share_pct(D(part), D(whole)) == want
