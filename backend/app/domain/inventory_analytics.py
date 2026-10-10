"""Inventory formulas (FM2 onward, docs/FINANCE_REVIEW.md F3, F15): stock adjustments by
reason, the value they take out of the business, and the input tax credit (ITC) to reverse on
goods lost. Pure functions; worked examples are in tests/unit/test_inventory_analytics.py.
Names follow docs/GLOSSARY.md and domain/kpi_catalogue.py."""

from collections import defaultdict, deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from app.domain.money import ZERO, Numberish, money, qty, to_decimal, unit_cost


class AdjustmentReason(StrEnum):
    """Why stock went up or down outside a bill, a purchase or a transfer."""

    WEIGHBRIDGE_GAIN = "weighbridge_gain"  # the weighbridge showed more than the bill
    WEIGHBRIDGE_LOSS = "weighbridge_loss"  # less than the bill, after the supplier was paid
    BREAKAGE = "breakage"  # torn cement bags, cracked pipes
    DAMAGE = "damage"  # rust, set cement, water damage
    THEFT = "theft"
    FREE_SAMPLE = "free_sample"  # given away to a customer or a mason
    COUNT_CORRECTION = "count_correction"  # a physical count differs from the books


class Direction(StrEnum):
    IN = "in"
    OUT = "out"


REASON_LABELS: dict[AdjustmentReason, str] = {
    AdjustmentReason.WEIGHBRIDGE_GAIN: "Weighbridge gain",
    AdjustmentReason.WEIGHBRIDGE_LOSS: "Weighbridge loss",
    AdjustmentReason.BREAKAGE: "Breakage",
    AdjustmentReason.DAMAGE: "Rust or damage",
    AdjustmentReason.THEFT: "Theft",
    AdjustmentReason.FREE_SAMPLE: "Free sample",
    AdjustmentReason.COUNT_CORRECTION: "Count correction",
}

_DIRECTIONS: dict[AdjustmentReason, frozenset[Direction]] = {
    AdjustmentReason.WEIGHBRIDGE_GAIN: frozenset({Direction.IN}),
    AdjustmentReason.COUNT_CORRECTION: frozenset({Direction.IN, Direction.OUT}),
}

# s.17(5)(h) CGST Act: no credit on goods lost, stolen, destroyed, written off or given away
# as gifts or free samples. Always reversed.
_ALWAYS_REVERSE = frozenset(
    {
        AdjustmentReason.BREAKAGE,
        AdjustmentReason.DAMAGE,
        AdjustmentReason.THEFT,
        AdjustmentReason.FREE_SAMPLE,
    }
)
# Unexplained shortages: the accountant confirms; the setting defaults to reversing them.
_SHORTAGES = frozenset({AdjustmentReason.WEIGHBRIDGE_LOSS, AdjustmentReason.COUNT_CORRECTION})


def allowed_directions(reason: AdjustmentReason) -> frozenset[Direction]:
    return _DIRECTIONS.get(reason, frozenset({Direction.OUT}))


def default_direction(reason: AdjustmentReason) -> Direction | None:
    """The only direction a reason allows; None when the user has to choose."""
    allowed = allowed_directions(reason)
    return next(iter(allowed)) if len(allowed) == 1 else None


def move_value(quantity: Numberish, unit_cost: Numberish) -> Decimal:
    """Rupees of stock moved: quantity in base units x weighted-average cost."""
    qty = to_decimal(quantity)
    if qty <= ZERO:
        raise ValueError("the quantity must be positive")
    return money(qty * to_decimal(unit_cost))


def itc_reversible(
    reason: AdjustmentReason, direction: Direction, *, reverse_shortages: bool
) -> bool:
    if direction is Direction.IN:
        return False
    if reason in _ALWAYS_REVERSE:
        return True
    return reverse_shortages and reason in _SHORTAGES


def itc_to_reverse(value: Numberish, gst_rate: Numberish) -> Decimal:
    """Input tax taken on goods that were lost: their cost x the item's GST rate."""
    return money(to_decimal(value) * to_decimal(gst_rate) / 100)


@dataclass(frozen=True)
class AdjustmentMove:
    reason: AdjustmentReason
    direction: Direction
    quantity: Decimal  # base units
    unit_cost: Decimal  # weighted average at the time of the move
    gst_rate: Decimal

    @property
    def value(self) -> Decimal:
        return move_value(self.quantity, self.unit_cost)

    @property
    def loss(self) -> Decimal:
        """Value lost (+) or gained (-)."""
        return self.value if self.direction is Direction.OUT else -self.value


def net_stock_loss(moves: Iterable[AdjustmentMove]) -> Decimal:
    """Stock value lost through adjustments less value gained; it reduces gross profit."""
    return money(sum((m.loss for m in moves), ZERO))


def loss_by_reason(moves: Iterable[AdjustmentMove]) -> dict[AdjustmentReason, Decimal]:
    total: dict[AdjustmentReason, Decimal] = defaultdict(lambda: ZERO)
    for m in moves:
        total[m.reason] += m.loss
    return dict(sorted(((r, money(v)) for r, v in total.items()), key=lambda x: -x[1]))


def total_itc_to_reverse(moves: Iterable[AdjustmentMove], *, reverse_shortages: bool) -> Decimal:
    return money(
        sum(
            (
                itc_to_reverse(m.value, m.gst_rate)
                for m in moves
                if itc_reversible(m.reason, m.direction, reverse_shortages=reverse_shortages)
            ),
            ZERO,
        )
    )


# ---------------------------------------------------------------------------- FM6: analytics


def abc_classes(consumption: Mapping[str, Decimal]) -> dict[str, str]:
    """ABC by value: items ranked by the cost of what was issued. An item is A while the share
    of the items ranked above it is under 80 %, B while it is under 95 %, else C. Items with no
    consumption get no class (dead stock shows up in the FSN and aging views instead)."""
    ranked = sorted(
        ((name, value) for name, value in consumption.items() if value > ZERO),
        key=lambda pair: (-pair[1], pair[0]),
    )
    total = sum((value for _, value in ranked), ZERO)
    classes: dict[str, str] = {}
    before = ZERO
    for name, value in ranked:
        classes[name] = (
            "A" if before * 100 < 80 * total else "B" if before * 100 < 95 * total else "C"
        )
        before += value
    return classes


def fsn_class(days_sold: int, *, fast_min_days: int) -> str:
    """Fast, slow or non-moving, by the number of days the item sold in the window. Stock
    adjustments are not sales and never count (the caller counts bills only)."""
    if days_sold <= 0:
        return "N"
    return "F" if days_sold >= fast_min_days else "S"


def age_bucket(days: int) -> str:
    """How long stock has sat since its last movement."""
    if days <= 30:
        return "0-30"
    if days <= 90:
        return "31-90"
    return "91-180" if days <= 180 else "180+"


def average_daily_sales(quantity: Numberish, days: int) -> Decimal | None:
    if days <= 0:
        return None
    return qty(to_decimal(quantity) / days)


def safety_stock(daily_sales: Numberish, safety_days: int) -> Decimal:
    """Stock held back for a bad week: so many days of average sales."""
    return qty(to_decimal(daily_sales) * safety_days)


def reorder_point(daily_sales: Numberish, lead_days: int, safety_days: int) -> Decimal:
    """Order when stock falls to what will be sold while the order is on the way, plus safety."""
    demand = to_decimal(daily_sales) * lead_days
    return qty(demand + to_decimal(safety_stock(daily_sales, safety_days)))


def cover_days(on_hand: Numberish, daily_sales: Numberish) -> Decimal | None:
    """How many days the stock will last at the recent pace; None when nothing is selling."""
    pace = to_decimal(daily_sales)
    if pace <= ZERO:
        return None
    return (to_decimal(on_hand) / pace).quantize(Decimal("0.1"), ROUND_HALF_UP)


def short_by(on_hand: Numberish, point: Numberish) -> Decimal:
    return qty(max(to_decimal(point) - to_decimal(on_hand), ZERO))


def needs_reorder(on_hand: Numberish, point: Numberish) -> bool:
    return to_decimal(on_hand) <= to_decimal(point)


def pick_days(*, item: int | None, supplier: int | None, default: int) -> int:
    """Lead time or safety days: the item's own setting, else its supplier's, else the shop's."""
    if item is not None:
        return item
    return supplier if supplier is not None else default


def has_history(first_movement: date | None, today: date, needed: int) -> bool:
    """Whether there are enough days of records to trust a rate; both end days count."""
    if first_movement is None:
        return False
    return (today - first_movement).days + 1 >= needed


def nrv_per_unit(market_rate: Numberish, cost_to_sell_pct: Numberish) -> Decimal:
    """Net realisable value: what a unit would fetch today, less the cost of selling it."""
    return unit_cost(to_decimal(market_rate) * (100 - to_decimal(cost_to_sell_pct)) / 100)


def nrv_loss(quantity: Numberish, average_cost: Numberish, nrv: Numberish) -> Decimal:
    """Lower of cost and NRV (AS 2): the loss when stock is worth less than cost, never a gain."""
    gap = to_decimal(average_cost) - to_decimal(nrv)
    return money(max(gap, ZERO) * to_decimal(quantity))


def holding_gain_loss(
    quantity: Numberish, average_cost: Numberish, replacement: Numberish
) -> Decimal:
    """What the stock on hand gained (+) or lost (-) against buying it again today."""
    return money((to_decimal(replacement) - to_decimal(average_cost)) * to_decimal(quantity))


def writedown_value(quantity: Numberish, old_cost: Numberish, new_cost: Numberish) -> Decimal:
    old, new = to_decimal(old_cost), to_decimal(new_cost)
    if new >= old:
        raise ValueError("a write-down must lower the cost")
    return money(to_decimal(quantity) * (old - new))


@dataclass(frozen=True)
class WritedownMove:
    place: str
    direction: Direction
    quantity: Decimal
    unit_cost: Decimal


def writedown_moves(
    by_location: Mapping[str, Decimal], old_cost: Numberish, new_cost: Numberish
) -> list[WritedownMove]:
    """Ledger rows for a write-down: all the stock out at the old average, then all of it back in
    at the new cost, so the average becomes the new cost whatever the places hold. Quantities do
    not change; places with nothing on hand are left out."""
    held = [(place, quantity) for place, quantity in by_location.items() if quantity > ZERO]
    old, new = to_decimal(old_cost), to_decimal(new_cost)
    return [WritedownMove(place, Direction.OUT, quantity, old) for place, quantity in held] + [
        WritedownMove(place, Direction.IN, quantity, new) for place, quantity in held
    ]


@dataclass(frozen=True)
class FifoMove:
    on: date
    qty_in: Decimal
    qty_out: Decimal


@dataclass(frozen=True)
class Layer:
    """Stock still on the shelf that came in on one day."""

    received: date
    quantity: Decimal

    def age_days(self, today: date) -> int:
        return (today - self.received).days


def fifo_layers(moves: Iterable[FifoMove]) -> list[Layer]:
    """What is left of each day's receipts if the oldest stock is always sold first. An estimate
    from receipts and issues (cement has no lot numbers); an issue with nothing left to take it
    from is ignored."""
    queue: deque[Layer] = deque()
    for move in sorted(moves, key=lambda m: (m.on, m.qty_in <= ZERO)):
        if move.qty_in > ZERO:
            queue.append(Layer(move.on, move.qty_in))
        left = move.qty_out
        while left > ZERO and queue:
            head = queue.popleft()
            if head.quantity > left:
                queue.appendleft(Layer(head.received, head.quantity - left))
                left = ZERO
            else:
                left -= head.quantity
    return list(queue)


AGE_BUCKETS = ("0-30", "31-60", "61-90", "90+")


def layer_buckets(layers: Iterable[Layer], today: date) -> dict[str, Decimal]:
    totals = dict.fromkeys(AGE_BUCKETS, ZERO)
    for layer in layers:
        days = layer.age_days(today)
        key = "0-30" if days <= 30 else "31-60" if days <= 60 else "61-90" if days <= 90 else "90+"
        totals[key] += layer.quantity
    return totals


def weight_loss_pct(billed: Numberish, received: Numberish) -> Decimal | None:
    """Billed less received over billed. Positive is a shortage, negative a gain."""
    base = to_decimal(billed)
    if base <= ZERO:
        return None
    return ((base - to_decimal(received)) / base * 100).quantize(Decimal("0.01"), ROUND_HALF_UP)


def shortage_value(billed: Numberish, received: Numberish, goods_value: Numberish) -> Decimal:
    """What the missing weight cost: its share of the goods value. Zero when nothing was short."""
    base, got = to_decimal(billed), to_decimal(received)
    if base <= ZERO or got >= base:
        return money(ZERO)
    return money(to_decimal(goods_value) * (base - got) / base)
