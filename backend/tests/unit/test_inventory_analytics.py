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


# ---------------------------------------------------------------- FM6: inventory analytics
#
# Consumption (cost of goods issued) over the last 90 days, six items, total ₹10,00,000:
#   TMT 12 mm 5,00,000 · TMT 10 mm 3,00,000 · Cement 1,00,000 · Pipe 60,000 · Wire 30,000 · Angle 10,000
#   share before each item: 0 %, 50 %, 80 %, 90 %, 96 %, 99 %
#   A while the share before is under 80 %, B under 95 %, then C:   A A B B C C
#
# Reorder (steel, tons): sold 36 t in the last 30 days = 1.2 t a day. Lead time 7 days, safety
# stock 2 days of sales: 1.2 x 7 + 1.2 x 2 = 8.4 + 2.4 = 10.8 t. On hand 9 t: short by 1.8 t.
# Cover = 9 ÷ 1.2 = 7.5 days.


def test_abc_classes_follow_the_cumulative_share_before_each_item() -> None:
    values = {
        "TMT 12 mm": D("500000"),
        "TMT 10 mm": D("300000"),
        "Cement": D("100000"),
        "Pipe": D("60000"),
        "Wire": D("30000"),
        "Angle": D("10000"),
    }
    classes = ia.abc_classes(values)
    assert classes == {
        "TMT 12 mm": "A",
        "TMT 10 mm": "A",
        "Cement": "B",
        "Pipe": "B",
        "Wire": "C",
        "Angle": "C",
    }


def test_one_big_item_is_class_a_and_items_nobody_bought_have_no_class() -> None:
    assert ia.abc_classes({"Only": D("100")}) == {"Only": "A"}
    out = ia.abc_classes({"Big": D("900"), "Small": D("100"), "Dead": D("0")})
    assert out == {"Big": "A", "Small": "B"}  # nothing is said about an item with no sales
    assert ia.abc_classes({}) == {}
    # Equal values are ordered by name, so the answer never depends on the input order: of four
    # items worth 50 each, the share before the fourth is 150 of 200 = 75 %, still under 80.
    forward = ia.abc_classes({"A": D("50"), "B": D("50"), "C": D("50"), "D": D("50")})
    backward = ia.abc_classes({"D": D("50"), "C": D("50"), "B": D("50"), "A": D("50")})
    assert forward == backward == {"A": "A", "B": "A", "C": "A", "D": "A"}
    # Five equal items: the fifth has 80 % before it, so it drops to B.
    five = ia.abc_classes(dict.fromkeys("ABCDE", D("20")))
    assert five["D"] == "A" and five["E"] == "B"


def test_fsn_counts_the_days_an_item_sold_in_the_window() -> None:
    assert ia.fsn_class(30, fast_min_days=15) == "F"
    assert ia.fsn_class(15, fast_min_days=15) == "F"
    assert ia.fsn_class(14, fast_min_days=15) == "S"
    assert ia.fsn_class(1, fast_min_days=15) == "S"
    assert ia.fsn_class(0, fast_min_days=15) == "N"  # non-moving


def test_age_buckets_run_from_the_last_movement() -> None:
    assert ia.age_bucket(0) == "0-30"
    assert ia.age_bucket(30) == "0-30"
    assert ia.age_bucket(31) == "31-90"
    assert ia.age_bucket(90) == "31-90"
    assert ia.age_bucket(91) == "91-180"
    assert ia.age_bucket(180) == "91-180"
    assert ia.age_bucket(181) == "180+"
    assert ia.age_bucket(-3) == "0-30"  # a movement dated ahead of today is not old


def test_reorder_point_is_lead_time_demand_plus_safety_stock() -> None:
    daily = ia.average_daily_sales(D("36000"), 30)  # 36 t in 30 days, in kg
    assert daily == D("1200.000")
    assert ia.safety_stock(daily, 2) == D("2400.000")
    assert ia.reorder_point(daily, 7, 2) == D("10800.000")  # 1.2 t x 7 + 2.4 t = 10.8 t
    assert ia.average_daily_sales(D("10"), 0) is None  # no days to divide by


def test_cover_days_and_how_short_an_item_is() -> None:
    assert ia.cover_days(D("9000"), D("1200")) == D("7.5")
    assert ia.cover_days(D("9000"), D("0")) is None  # nothing sold: cover is not defined
    assert ia.short_by(D("9000"), D("10800")) == D("1800.000")
    assert ia.short_by(D("12000"), D("10800")) == D("0.000")
    assert ia.needs_reorder(D("9000"), D("10800")) is True
    assert ia.needs_reorder(D("10800"), D("10800")) is True  # at the point: order now
    assert ia.needs_reorder(D("10801"), D("10800")) is False


def test_the_lead_time_comes_from_the_item_then_the_supplier_then_the_shop() -> None:
    assert ia.pick_days(item=3, supplier=5, default=7) == 3
    assert ia.pick_days(item=None, supplier=5, default=7) == 5
    assert ia.pick_days(item=None, supplier=None, default=7) == 7
    assert ia.pick_days(item=0, supplier=5, default=7) == 0  # zero is a real answer


def test_enough_history_needs_thirty_days() -> None:
    from datetime import date

    today = date(2026, 10, 30)
    assert ia.has_history(date(2026, 10, 1), today, 30) is True  # 30 days, counting both ends
    assert ia.has_history(date(2026, 10, 2), today, 30) is False  # 29
    assert ia.has_history(None, today, 30) is False  # nothing has moved yet


# NRV: TMT on hand 31,000 kg at an average cost of ₹55. The market rate falls to ₹54 a kg.
#   NRV = 54 x (1 - 0 %) = ₹54; loss = (55 - 54) x 31,000 = ₹31,000
#   with 1 % costs to sell: NRV = 54 x 0.99 = ₹53.46; loss = 1.54 x 31,000 = ₹47,740
#   a market rate above cost: no loss (cost is the lower figure) and no write-down.
# Replacement cost ₹56 (the last purchase): holding gain = (56 - 55) x 31,000 = +₹31,000.


def test_nrv_is_the_market_rate_less_the_costs_to_sell() -> None:
    assert ia.nrv_per_unit(D("54"), D("0")) == D("54.0000")
    assert ia.nrv_per_unit(D("54"), D("1")) == D("53.4600")


def test_the_nrv_loss_only_counts_when_the_market_is_below_cost() -> None:
    assert ia.nrv_loss(D("31000"), D("55"), D("54")) == D("31000.00")
    assert ia.nrv_loss(D("31000"), D("55"), D("53.46")) == D("47740.00")
    assert ia.nrv_loss(D("31000"), D("55"), D("57")) == D("0.00")  # never written up


def test_holding_gain_or_loss_against_the_replacement_cost() -> None:
    assert ia.holding_gain_loss(D("31000"), D("55"), D("56")) == D("31000.00")
    assert ia.holding_gain_loss(D("31000"), D("55"), D("52.5")) == D("-77500.00")


def test_a_write_down_replaces_the_average_without_moving_any_quantity() -> None:
    """TMT: 5,000 kg at the shop, 20,000 kg at the godown, average ₹55. Writing down to ₹54 is,
    place by place, the stock out at the average and the same stock in at ₹54: quantities stay,
    the average becomes ₹54 and the stock is worth ₹25,000 less."""
    from datetime import date

    from app.domain.stock_valuation import StockMove, replay

    day = date(2026, 10, 1)
    moves = [
        StockMove(day, "S1", D("5000"), D("0"), D("55")),
        StockMove(day, "G1", D("20000"), D("0"), D("55")),
    ]
    before = replay(moves)
    assert before.total.value == D("1375000.00")
    pairs = ia.writedown_moves({"S1": D("5000"), "G1": D("20000")}, D("55"), D("54"))
    # All the stock goes out at the average, then comes back at ₹54, so no place is left holding
    # a mix of the old and the new cost.
    assert [(m.place, m.direction, m.quantity, m.unit_cost) for m in pairs] == [
        ("S1", Dir.OUT, D("5000"), D("55")),
        ("G1", Dir.OUT, D("20000"), D("55")),
        ("S1", Dir.IN, D("5000"), D("54")),
        ("G1", Dir.IN, D("20000"), D("54")),
    ]
    for m in pairs:
        moves.append(
            StockMove(
                date(2026, 10, 2),
                m.place,
                m.quantity if m.direction is Dir.IN else D("0"),
                m.quantity if m.direction is Dir.OUT else D("0"),
                m.unit_cost,
            )
        )
    after = replay(moves)
    assert after.by_location == {"S1": D("5000.000"), "G1": D("20000.000")}
    assert after.total.avg_cost == D("54.0000")
    assert before.total.value - after.total.value == ia.writedown_value(
        D("25000"), D("55"), D("54")
    )
    assert ia.writedown_value(D("25000"), D("55"), D("54")) == D("25000.00")


def test_a_write_down_must_lower_the_cost_and_skips_empty_places() -> None:
    with pytest.raises(ValueError, match="lower"):
        ia.writedown_value(D("10"), D("55"), D("55"))
    only = ia.writedown_moves({"S1": D("0"), "G1": D("4")}, D("55"), D("54"))
    assert [(m.place, m.direction) for m in only] == [("G1", Dir.OUT), ("G1", Dir.IN)]


# FIFO proxy for cement (bags), on 20 October:
#   in  15 Jul 100 · 25 Aug 200 · 20 Sep 300
#   out  1 Sep 150 (takes the 100 of July, then 50 of August) · 1 Oct 100 (the rest of August's 150)
#   left: 50 bags from 25 Aug (56 days old) and 300 from 20 Sep (30 days old)


def test_fifo_layers_take_the_oldest_stock_first() -> None:
    from datetime import date

    moves = [
        ia.FifoMove(date(2026, 7, 15), D("100"), D("0")),
        ia.FifoMove(date(2026, 8, 25), D("200"), D("0")),
        ia.FifoMove(date(2026, 9, 20), D("300"), D("0")),
        ia.FifoMove(date(2026, 9, 1), D("0"), D("150")),
        ia.FifoMove(date(2026, 10, 1), D("0"), D("100")),
    ]
    layers = ia.fifo_layers(moves)
    assert [(x.received, x.quantity) for x in layers] == [
        (date(2026, 8, 25), D("50")),
        (date(2026, 9, 20), D("300")),
    ]
    today = date(2026, 10, 20)
    assert [x.age_days(today) for x in layers] == [56, 30]
    assert ia.layer_buckets(layers, today) == {
        "0-30": D("300"),
        "31-60": D("50"),
        "61-90": D("0"),
        "90+": D("0"),
    }


def test_old_cement_shows_up_in_the_oldest_bucket() -> None:
    from datetime import date

    moves = [
        ia.FifoMove(date(2026, 7, 15), D("100"), D("0")),
        ia.FifoMove(date(2026, 9, 20), D("300"), D("0")),
        ia.FifoMove(date(2026, 10, 1), D("0"), D("50")),  # sold from the old stack first
    ]
    today = date(2026, 10, 20)
    layers = ia.fifo_layers(moves)
    assert [(x.received, x.quantity) for x in layers] == [
        (date(2026, 7, 15), D("50")),
        (date(2026, 9, 20), D("300")),
    ]
    buckets = ia.layer_buckets(layers, today)
    assert buckets["90+"] == D("50") and buckets["0-30"] == D("300")
    # More sold than was ever received (an opening balance was missed): the shortfall is ignored.
    assert ia.fifo_layers([ia.FifoMove(date(2026, 10, 1), D("0"), D("5"))]) == []


# Shrinkage by supplier: 10 ton billed, 9.94 ton on the weighbridge, goods ₹5,50,000.
#   loss = (10,000 - 9,940) ÷ 10,000 = 0.60 %; value = 5,50,000 x 60 ÷ 10,000 = ₹3,300


def test_weight_loss_is_billed_less_received_over_billed() -> None:
    assert ia.weight_loss_pct(D("10000"), D("9940")) == D("0.60")
    assert ia.weight_loss_pct(D("10000"), D("10020")) == D("-0.20")  # a gain
    assert ia.weight_loss_pct(D("0"), D("0")) is None


def test_the_value_of_a_shortage_is_its_share_of_the_goods_value() -> None:
    assert ia.shortage_value(D("10000"), D("9940"), D("550000")) == D("3300.00")
    assert ia.shortage_value(D("10000"), D("10020"), D("550000")) == D("0.00")  # no shortage
    assert ia.shortage_value(D("0"), D("0"), D("0")) == D("0.00")


def test_the_inventory_kpis_are_in_the_catalogue() -> None:
    from app.domain import kpi_catalogue as cat

    wanted = {
        "stock_cover_days",
        "reorder_point",
        "safety_stock",
        "weight_loss_pct",
        "nrv",
        "holding_gain_loss",
        "nrv_writedown",
        "dead_stock_value",
        "shrinkage_value",
    }
    assert wanted <= {k.code for k in cat.CATALOGUE}
    staff = {k.code for k in cat.definitions(owner=False)}
    assert {"stock_cover_days", "reorder_point", "weight_loss_pct"} <= staff
    for code in (
        "nrv",
        "holding_gain_loss",
        "nrv_writedown",
        "dead_stock_value",
        "shrinkage_value",
    ):
        assert code not in staff
