"""Direct fulfilment (Milestone 9, rule B10): a sale delivered straight from the supplier to the
customer's site moves no stock. Its profit is the sale less what the supplier charged for the
goods less the freight."""

from decimal import Decimal

from app.domain.money import ZERO, money, qty, to_decimal


def profit(
    taxable: Decimal, base_qty: Decimal, unit_cost: Decimal, freight: Decimal = ZERO
) -> Decimal:
    """Sale (excluding GST) less goods at landed cost less freight, to paise."""
    return money(
        to_decimal(taxable) - to_decimal(base_qty) * to_decimal(unit_cost) - to_decimal(freight)
    )


def remaining_to_link(billed_qty: Decimal, linked: list[Decimal]) -> Decimal:
    """What is left of a direct purchase line that no sale has claimed yet."""
    return qty(to_decimal(billed_qty) - sum(linked, ZERO))


def check_link(billed_qty: Decimal, linked: list[Decimal], wanted: Decimal, unit: str = "") -> None:
    """Raise ValueError unless `wanted` is positive and fits in what is left."""
    if wanted <= ZERO:
        raise ValueError("the linked quantity must be positive")
    left = remaining_to_link(billed_qty, linked)
    if wanted > left:
        raise ValueError(f"only {left.normalize():f} {unit}".rstrip() + " of this purchase is free")
