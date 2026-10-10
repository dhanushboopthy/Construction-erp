"""Orders, lots and demand (FM10, docs/FINANCE_REVIEW.md F25, F26): the three-way match of a
purchase order, the goods received and the supplier's bill; cement lots by manufacturing week
and the oldest-first pick; and the fill rate. Pure functions; worked examples are in
tests/unit/test_orders.py."""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.domain.money import ZERO, Numberish, money, to_decimal

_HUNDRED = Decimal(100)


def _pct(part: Decimal, whole: Decimal) -> Decimal | None:
    if whole == ZERO:
        return None
    return (part / whole * _HUNDRED).quantize(Decimal("0.01"), ROUND_HALF_UP)


@dataclass(frozen=True)
class LineMatch:
    qty_over_received_pct: Decimal | None  # billed beyond what the weighbridge/GRN recorded
    over_received: bool
    over_ordered: bool
    rate_variance_pct: Decimal | None  # bill rate against the order rate (plus is dearer)
    rate_exception: bool
    ppv: Decimal  # (bill rate - order rate) x quantity on this bill; plus is a loss
    ok: bool
    reasons: list[str]


def match_line(
    *,
    ordered: Numberish,
    received: Numberish,
    billed: Numberish,
    this_billed: Numberish,
    po_rate: Numberish,
    bill_rate: Numberish,
    qty_tolerance_pct: Numberish,
    rate_tolerance_pct: Numberish,
) -> LineMatch:
    """Match one item. Quantities are in base units, rates per base unit; `billed` is everything
    billed on the order including this bill, `this_billed` only this bill's quantity.

    The bill must not claim more than was received or ordered beyond the quantity tolerance, and
    must not charge more than the order rate beyond the rate tolerance. Billing less than was
    received, or at a lower rate, is no risk. A zero tolerance means exactly."""
    ord_q, rec_q, bill_q = to_decimal(ordered), to_decimal(received), to_decimal(billed)
    order_rate, billed_rate = to_decimal(po_rate), to_decimal(bill_rate)
    q_room = _HUNDRED + to_decimal(qty_tolerance_pct)
    r_room = _HUNDRED + to_decimal(rate_tolerance_pct)
    reasons: list[str] = []

    over_received = bill_q * _HUNDRED > rec_q * q_room
    over_pct = _pct(bill_q - rec_q, rec_q) if bill_q > rec_q else None
    if over_received:
        reasons.append(
            "The bill is for more than was received."
            if rec_q > ZERO
            else "The bill is for goods, but nothing has been received on this order."
        )
    over_ordered = bill_q * _HUNDRED > ord_q * q_room
    if over_ordered:
        reasons.append("The bill is for more than was ordered.")

    variance = _pct(billed_rate - order_rate, order_rate)
    rate_exception = billed_rate * _HUNDRED > order_rate * r_room and order_rate > ZERO
    if rate_exception:
        reasons.append("The rate is higher than the order rate.")

    return LineMatch(
        qty_over_received_pct=over_pct,
        over_received=over_received,
        over_ordered=over_ordered,
        rate_variance_pct=variance,
        rate_exception=rate_exception,
        ppv=money((billed_rate - order_rate) * to_decimal(this_billed)),
        ok=not reasons,
        reasons=reasons,
    )


# ---------------------------------------------------------------------------- cement lots


def lot_date(year: int, week: int) -> date:
    """The Monday of an ISO week: the date an unmarked bag is assumed to be made, for ordering."""
    try:
        return date.fromisocalendar(year, week, 1)
    except ValueError as exc:
        raise ValueError(f"{year} has no week {week}") from exc


def lot_label(week: int | None, year: int | None, received_on: date) -> str:
    """How a lot reads on screen: the printed week, or the day it came in when none was marked."""
    if week is not None and year is not None:
        return f"Week {week}, {year}"
    return f"Received {received_on:%d-%m-%Y}"


@dataclass(frozen=True)
class Layer:
    """Stock that came in on one purchase line and has not been sold yet. `key` orders layers:
    the Monday of the printed week, or the receipt date when no week is printed."""

    id: int
    key: date
    remaining: Decimal


@dataclass(frozen=True)
class Pick:
    layer_id: int
    quantity: Decimal


def fifo_pick(layers: list[Layer], on_hand: Numberish, quantity: Numberish) -> list[Pick]:
    """Take `quantity` oldest layer first. `on_hand` is what the ledger says is at the place.

    Stock the layers do not account for (opening stock, returns, transfers in) is older than the
    lots we know, so it is sold first. If less is on hand than the layers hold, the difference
    left some other way (transfer, theft, count) and is taken off the oldest layers first."""
    here = to_decimal(on_hand)
    ordered = sorted(layers, key=lambda x: (x.key, x.id))
    held = sum((x.remaining for x in ordered), ZERO)
    shed = max(held - here, ZERO)
    available: list[tuple[Layer, Decimal]] = []
    for layer in ordered:
        gone = min(layer.remaining, shed)
        shed -= gone
        left = layer.remaining - gone
        if left > ZERO:
            available.append((layer, left))
    unlisted = max(here - held, ZERO)
    need = max(to_decimal(quantity) - unlisted, ZERO)
    picks: list[Pick] = []
    for layer, left in available:
        if need <= ZERO:
            break
        take = min(left, need)
        picks.append(Pick(layer.id, take))
        need -= take
    return picks


# ---------------------------------------------------------------------------- demand


def fill_rate_pct(supplied: Numberish, lost: Numberish) -> Decimal | None:
    """Quantity supplied ÷ quantity asked for (supplied plus the lost-sales log) x 100. None when
    nothing was asked for."""
    supplied_q, lost_q = to_decimal(supplied), to_decimal(lost)
    return _pct(supplied_q, supplied_q + lost_q)
