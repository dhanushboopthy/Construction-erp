"""Returns (Milestone 8, rule B11): a credit note (customer) or debit note (supplier) takes back a
share of an invoiced line. The value is pro rata to the quantity, so a full return reverses the
line exactly and GST is worked out again on the returned value."""

from decimal import Decimal

from app.domain.money import ZERO, money, to_decimal


def returned_taxable(line_taxable: Decimal, line_qty: Decimal, returned_qty: Decimal) -> Decimal:
    """Share of a line's taxable value for `returned_qty` of `line_qty`, to paise, half up."""
    if returned_qty == line_qty:
        return money(line_taxable)
    return money(to_decimal(line_taxable) * returned_qty / line_qty)


def check_returnable(sold: Decimal, already_returned: Decimal, requested: Decimal) -> None:
    """Raise ValueError if `requested` is not positive or is more than is left to return."""
    if requested <= ZERO:
        raise ValueError("the returned quantity must be positive")
    left = sold - already_returned
    if requested > left:
        raise ValueError(f"only {left.normalize():f} can still be returned")
