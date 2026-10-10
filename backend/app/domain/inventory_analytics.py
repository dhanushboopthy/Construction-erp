"""Inventory formulas (FM2 onward, docs/FINANCE_REVIEW.md F3, F15): stock adjustments by
reason, the value they take out of the business, and the input tax credit (ITC) to reverse on
goods lost. Pure functions; worked examples are in tests/unit/test_inventory_analytics.py.
Names follow docs/GLOSSARY.md and domain/kpi_catalogue.py."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.domain.money import ZERO, Numberish, money, to_decimal


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
