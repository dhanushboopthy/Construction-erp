"""Daily closing (Milestone 12, B12): the cash drawer and the day's figures."""

from datetime import date
from decimal import Decimal

from app.domain.money import ZERO, Numberish, money, to_decimal


def expected_cash(opening: Numberish, cash_in: Numberish, cash_out: Numberish) -> Decimal:
    """Cash that should be in the drawer: what it started with plus receipts less payments."""
    return money(to_decimal(opening) + to_decimal(cash_in) - to_decimal(cash_out))


def cash_difference(counted: Numberish, expected: Numberish) -> Decimal:
    """Counted less expected: negative means the drawer is short."""
    if to_decimal(counted) < ZERO:
        raise ValueError("the counted cash cannot be negative")
    return money(to_decimal(counted) - to_decimal(expected))


def note_needed(difference: Numberish) -> bool:
    """Any difference, over or short, has to be explained before the day is closed."""
    return money(difference) != ZERO


def month_key(on: date) -> str:
    return f"{on.year:04d}-{on.month:02d}"
