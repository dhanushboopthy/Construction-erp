"""Orders, lots and demand (FM10). Hand-worked numbers.

Three-way match, TMT from Mills. The order: 10 t at ₹55,000 a ton (₹55 a kg). Tolerances 1 %
on quantity and 0.5 % on rate.
  goods received 9.95 t (the weighbridge); bill for 10 t:
    billed 10,000 kg against received 9,950 kg: 50 kg over = 50 ÷ 9,950 = 0.50 % -> within 1 %
  goods received 9.8 t; bill for 10 t:
    200 kg over = 200 ÷ 9,800 = 2.04 % -> over the tolerance, needs the owner
  nothing received yet; bill for 10 t: over, however small the tolerance
  bill rate ₹55,200 a ton: (55.20 - 55) ÷ 55 = 0.36 % -> within 0.5 %; PPV = 0.20 x 10,000 = ₹2,000
  bill rate ₹55,500 a ton: 0.91 % -> over; PPV = 0.50 x 10,000 = ₹5,000
  bill rate ₹54,500 a ton: below the order is no risk; PPV = -0.50 x 10,000 = -₹5,000

Cement lots. At the shop: week 30 of 2026 (40 bags left), week 35 (60 bags), and a delivery with
no week printed, received 01-10-2026 (20 bags). 120 on hand. Selling 50 bags takes the oldest
first: 40 from week 30 and 10 from week 35. Week 30 of 2026 starts Monday 20-07-2026.

Fill rate: 90 bags supplied and 10 asked for but out of stock = 90 ÷ 100 = 90 %.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.domain import orders as o

D = Decimal


def match(received: str, bill_rate: str = "55", billed: str = "10000", ordered: str = "10000"):
    return o.match_line(
        ordered=D(ordered),
        received=D(received),
        billed=D(billed),
        this_billed=D(billed),
        po_rate=D("55"),
        bill_rate=D(bill_rate),
        qty_tolerance_pct=D("1"),
        rate_tolerance_pct=D("0.5"),
    )


def test_a_small_weighbridge_difference_is_within_tolerance() -> None:
    m = match("9950")
    assert m.qty_over_received_pct == D("0.50")
    assert m.ok and m.reasons == []


def test_billing_more_than_was_received_needs_the_owner() -> None:
    m = match("9800")
    assert m.qty_over_received_pct == D("2.04")
    assert not m.ok and m.over_received and not m.over_ordered
    assert "more than was received" in m.reasons[0]


def test_billing_before_anything_is_received_is_over() -> None:
    m = match("0")
    assert m.over_received and not m.ok
    assert m.qty_over_received_pct is None  # nothing to divide by
    assert "nothing" in m.reasons[0]


def test_billing_less_than_received_is_fine() -> None:
    m = match("10000", billed="6000")
    assert m.ok and m.qty_over_received_pct is None


def test_billing_more_than_ordered_is_over_even_if_received() -> None:
    m = match("10300", billed="10300", ordered="10000")
    assert m.over_ordered and not m.over_received
    assert not m.ok and "more than was ordered" in m.reasons[0]


@pytest.mark.parametrize(
    ("rate", "variance", "ppv", "ok"),
    [
        ("55.20", "0.36", "2000.00", True),
        ("55.50", "0.91", "5000.00", False),
        ("54.50", "-0.91", "-5000.00", True),
        ("55", "0.00", "0.00", True),
    ],
)
def test_rate_against_the_order_and_ppv(rate: str, variance: str, ppv: str, ok: bool) -> None:
    m = match("10000", bill_rate=rate)
    assert m.rate_variance_pct == D(variance)
    assert m.ppv == D(ppv)
    assert m.ok is ok
    assert m.rate_exception is (not ok)


def test_an_order_with_no_rate_has_no_rate_variance() -> None:
    m = o.match_line(
        ordered=D("10"),
        received=D("10"),
        billed=D("10"),
        this_billed=D("10"),
        po_rate=D("0"),
        bill_rate=D("5"),
        qty_tolerance_pct=D("1"),
        rate_tolerance_pct=D("0"),
    )
    assert m.rate_variance_pct is None and m.ok and m.ppv == D("50.00")


def test_zero_tolerance_means_exact() -> None:
    m = o.match_line(
        ordered=D("100"),
        received=D("100"),
        billed=D("100.001"),
        this_billed=D("100.001"),
        po_rate=D("10"),
        bill_rate=D("10"),
        qty_tolerance_pct=D("0"),
        rate_tolerance_pct=D("0"),
    )
    assert not m.ok


# ---------------------------------------------------------------- lots


def test_a_lot_is_the_monday_of_its_week() -> None:
    assert o.lot_date(2026, 30) == date(2026, 7, 20)
    assert o.lot_date(2026, 1) == date(2025, 12, 29)  # ISO week 1 can start in December
    with pytest.raises(ValueError, match="week"):
        o.lot_date(2025, 53)  # 2025 has 52 ISO weeks
    with pytest.raises(ValueError, match="week"):
        o.lot_date(2026, 0)


def test_lot_label() -> None:
    assert o.lot_label(30, 2026, date(2026, 10, 1)) == "Week 30, 2026"
    assert o.lot_label(None, None, date(2026, 10, 1)) == "Received 01-10-2026"


def layers() -> list[o.Layer]:
    return [
        o.Layer(id=3, key=date(2026, 10, 1), remaining=D("20")),  # no week printed
        o.Layer(id=2, key=o.lot_date(2026, 35), remaining=D("60")),
        o.Layer(id=1, key=o.lot_date(2026, 30), remaining=D("40")),
    ]


def test_oldest_week_is_sold_first() -> None:
    picks = o.fifo_pick(layers(), on_hand=D("120"), quantity=D("50"))
    assert [(p.layer_id, p.quantity) for p in picks] == [(1, D("40")), (2, D("10"))]


def test_a_delivery_without_a_week_falls_back_to_its_receipt_date() -> None:
    picks = o.fifo_pick(layers(), on_hand=D("120"), quantity=D("110"))
    assert [(p.layer_id, p.quantity) for p in picks] == [(1, D("40")), (2, D("60")), (3, D("10"))]


def test_stock_with_no_lot_record_goes_first() -> None:
    # 150 on hand but the lots only account for 120: the other 30 (opening stock, returns) are
    # the oldest, so selling 50 takes 30 of them and 20 from week 30.
    picks = o.fifo_pick(layers(), on_hand=D("150"), quantity=D("50"))
    assert [(p.layer_id, p.quantity) for p in picks] == [(1, D("20"))]


def test_stock_that_left_by_other_ways_is_taken_off_the_oldest_lots() -> None:
    # Only 100 on hand though the lots say 120: 20 left (transfer, theft); the oldest lot
    # loses them, so selling 50 takes 20 left of week 30 and 30 of week 35.
    picks = o.fifo_pick(layers(), on_hand=D("100"), quantity=D("50"))
    assert [(p.layer_id, p.quantity) for p in picks] == [(1, D("20")), (2, D("30"))]


def test_nothing_to_pick_when_there_is_no_lot_stock() -> None:
    assert o.fifo_pick([], on_hand=D("10"), quantity=D("5")) == []
    assert o.fifo_pick(layers(), on_hand=D("0"), quantity=D("5")) == []


def test_asking_for_more_than_the_lots_hold_picks_what_exists() -> None:
    picks = o.fifo_pick(layers(), on_hand=D("120"), quantity=D("500"))
    assert sum((p.quantity for p in picks), D("0")) == D("120")


# ---------------------------------------------------------------- fill rate


def test_fill_rate() -> None:
    assert o.fill_rate_pct(D("90"), D("10")) == D("90.00")
    assert o.fill_rate_pct(D("0"), D("10")) == D("0.00")
    assert o.fill_rate_pct(D("5"), D("0")) == D("100.00")
    assert o.fill_rate_pct(D("0"), D("0")) is None  # nothing was asked for
