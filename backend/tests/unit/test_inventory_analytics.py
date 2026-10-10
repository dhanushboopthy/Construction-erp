"""Stock adjustments (FM2). Hand-worked numbers for one month at the shop.

October adjustments, all items at 18% GST:
  breakage       2 bags cement x ₹380      out   ₹760.00
  theft          200 kg binding wire x ₹75 out   ₹15,000.00
  weighbridge    40 kg TMT gained x ₹6     in    ₹240.00
  count          19 bags short x ₹60       out   ₹1,140.00
  net stock lost = 760 + 15,000 + 1,140 - 240 = ₹16,660.00

ITC to reverse (CGST Act s.17(5)(h): goods lost, stolen, destroyed or given as free samples):
  breakage 760 x 18% = 136.80 · theft 15,000 x 18% = 2,700.00
  shortages (count, weighbridge loss) only when the setting says so (default yes):
  count 1,140 x 18% = 205.20
  total with shortages = 136.80 + 2,700.00 + 205.20 = ₹3,042.00; without = ₹2,836.80
  a gain is never reversed.

Profit and loss with the adjustments:
  gross profit before stock loss ₹70,000 (tests/unit/test_finance.py) - 16,660 = ₹53,340.00
"""

from decimal import Decimal

import pytest

from app.domain import finance as f
from app.domain import inventory_analytics as ia
from app.domain.inventory_analytics import AdjustmentReason as R
from app.domain.inventory_analytics import Direction as Dir

D = Decimal

OCTOBER = [
    ia.AdjustmentMove(R.BREAKAGE, Dir.OUT, D("2"), D("380"), D("18")),
    ia.AdjustmentMove(R.THEFT, Dir.OUT, D("200"), D("75"), D("18")),
    ia.AdjustmentMove(R.WEIGHBRIDGE_GAIN, Dir.IN, D("40"), D("6"), D("18")),
    ia.AdjustmentMove(R.COUNT_CORRECTION, Dir.OUT, D("19"), D("60"), D("18")),
]


def test_acceptance_breakage_of_two_bags_is_760() -> None:
    assert ia.move_value(D("2"), D("380")) == D("760.00")


def test_acceptance_theft_of_15000_reverses_2700_itc() -> None:
    value = ia.move_value(D("200"), D("75"))
    assert value == D("15000.00")
    assert ia.itc_reversible(R.THEFT, Dir.OUT, reverse_shortages=False)
    assert ia.itc_to_reverse(value, D("18")) == D("2700.00")


def test_net_stock_lost_in_october() -> None:
    assert ia.net_stock_loss(OCTOBER) == D("16660.00")


def test_loss_by_reason_signs_gains_negative() -> None:
    assert ia.loss_by_reason(OCTOBER) == {
        R.THEFT: D("15000.00"),
        R.COUNT_CORRECTION: D("1140.00"),
        R.BREAKAGE: D("760.00"),
        R.WEIGHBRIDGE_GAIN: D("-240.00"),
    }


def test_itc_to_reverse_in_october_with_and_without_shortages() -> None:
    assert ia.total_itc_to_reverse(OCTOBER, reverse_shortages=True) == D("3042.00")
    assert ia.total_itc_to_reverse(OCTOBER, reverse_shortages=False) == D("2836.80")


@pytest.mark.parametrize(
    ("reason", "direction", "shortages", "expected"),
    [
        (R.BREAKAGE, Dir.OUT, False, True),
        (R.DAMAGE, Dir.OUT, False, True),
        (R.THEFT, Dir.OUT, False, True),
        (R.FREE_SAMPLE, Dir.OUT, False, True),
        (R.WEIGHBRIDGE_LOSS, Dir.OUT, False, False),
        (R.WEIGHBRIDGE_LOSS, Dir.OUT, True, True),
        (R.COUNT_CORRECTION, Dir.OUT, False, False),
        (R.COUNT_CORRECTION, Dir.OUT, True, True),
        (R.COUNT_CORRECTION, Dir.IN, True, False),
        (R.WEIGHBRIDGE_GAIN, Dir.IN, True, False),
    ],
)
def test_which_moves_reverse_itc(
    reason: R, direction: Dir, shortages: bool, expected: bool
) -> None:
    assert ia.itc_reversible(reason, direction, reverse_shortages=shortages) is expected


def test_each_reason_has_its_directions() -> None:
    assert ia.allowed_directions(R.WEIGHBRIDGE_GAIN) == frozenset({Dir.IN})
    assert ia.allowed_directions(R.COUNT_CORRECTION) == frozenset({Dir.IN, Dir.OUT})
    for reason in (R.WEIGHBRIDGE_LOSS, R.BREAKAGE, R.DAMAGE, R.THEFT, R.FREE_SAMPLE):
        assert ia.allowed_directions(reason) == frozenset({Dir.OUT})
    assert set(ia.REASON_LABELS) == set(R)


def test_default_direction_only_when_there_is_one() -> None:
    assert ia.default_direction(R.THEFT) is Dir.OUT
    assert ia.default_direction(R.WEIGHBRIDGE_GAIN) is Dir.IN
    assert ia.default_direction(R.COUNT_CORRECTION) is None


def test_quantity_must_be_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        ia.move_value(D("0"), D("380"))


def test_gross_profit_and_contribution_carry_the_stock_loss() -> None:
    loss = ia.net_stock_loss(OCTOBER)
    assert f.gross_profit(D("1950000"), D("1860000"), D("20000"), loss) == D("53340.00")
    assert f.contribution(D("1950000"), D("1860000"), D("20000"), D("8000"), loss) == D("45340.00")
    # Without adjustments the FM1 figures are unchanged.
    assert f.gross_profit(D("1950000"), D("1860000"), D("20000")) == D("70000.00")
