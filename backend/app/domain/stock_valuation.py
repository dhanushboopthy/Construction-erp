"""Weighted-average stock cost (rule: one average per item across all locations, gap fix G6).

Quantity is tracked per location, but the average cost is company-wide, so moving stock
between a shop and the godown never changes its value.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.domain.money import ZERO, Numberish, qty, to_decimal, unit_cost


class NegativeStockError(ValueError):
    pass


@dataclass(frozen=True)
class StockPosition:
    quantity: Decimal
    avg_cost: Decimal

    @property
    def value(self) -> Decimal:
        return (self.quantity * self.avg_cost).quantize(Decimal("0.01"))


EMPTY = StockPosition(ZERO, ZERO)


def receive(position: StockPosition, quantity: Numberish, cost: Numberish) -> StockPosition:
    """Stock in at `cost` per base unit; the average moves toward the new cost."""
    q_in, c_in = to_decimal(quantity), to_decimal(cost)
    if q_in <= ZERO:
        raise ValueError("received quantity must be positive")
    if c_in < ZERO:
        raise ValueError("cost cannot be negative")
    if position.quantity <= ZERO:
        return StockPosition(qty(position.quantity + q_in), unit_cost(c_in))
    new_qty = position.quantity + q_in
    new_avg = (position.quantity * position.avg_cost + q_in * c_in) / new_qty
    return StockPosition(qty(new_qty), unit_cost(new_avg))


def issue(position: StockPosition, quantity: Numberish) -> StockPosition:
    """Stock out at the current average. The average itself does not change."""
    q_out = to_decimal(quantity)
    if q_out <= ZERO:
        raise ValueError("issued quantity must be positive")
    if q_out > position.quantity:
        raise NegativeStockError(
            f"only {position.quantity} in stock, cannot issue {q_out} (rule B13)"
        )
    return StockPosition(qty(position.quantity - q_out), position.avg_cost)


@dataclass(frozen=True)
class StockMove:
    """One row of the stock ledger as the domain sees it (never edited, only appended)."""

    entry_date: date
    location: str
    qty_in: Decimal
    qty_out: Decimal
    unit_cost: Decimal


@dataclass(frozen=True)
class Replay:
    total: StockPosition  # all locations together: quantity and the company-wide average cost
    by_location: dict[str, Decimal] = field(default_factory=dict)


def replay(moves: list[StockMove]) -> Replay:
    """Rebuild quantity and average cost from the ledger (G6).

    One average per item for the whole business; quantity is also kept per location. Moves are
    taken by date, then in the order given. A transfer is an out and an in at the average, so
    it never changes the average. When stock runs out the next receipt sets the cost."""
    position = EMPTY
    per_location: dict[str, Decimal] = {}
    for _index, move in sorted(enumerate(moves), key=lambda p: (p[1].entry_date, p[0])):
        if move.qty_in > ZERO:
            position = receive(position, move.qty_in, move.unit_cost)
        if move.qty_out > ZERO:
            position = issue(position, move.qty_out)
        per_location[move.location] = (
            per_location.get(move.location, ZERO) + move.qty_in - move.qty_out
        )
    return Replay(position, {k: qty(v) for k, v in per_location.items()})
