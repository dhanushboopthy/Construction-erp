"""Decimal helpers. Floats are rejected on purpose: 0.1 + 0.2 != 0.3 has no place on a bill."""

from decimal import ROUND_HALF_UP, Decimal

MONEY_PLACES = Decimal("0.01")
QTY_PLACES = Decimal("0.001")
UNIT_COST_PLACES = Decimal("0.0001")
RUPEE = Decimal("1")

ZERO = Decimal("0")

type Numberish = Decimal | int | str


def to_decimal(value: Numberish) -> Decimal:
    if isinstance(value, float):
        raise TypeError("Use Decimal or str for money and quantities, never float")
    if isinstance(value, bool):
        raise TypeError("bool is not a number here")
    return value if isinstance(value, Decimal) else Decimal(value)


def money(value: Numberish) -> Decimal:
    """Round to paise, half up (the usual commercial rounding)."""
    return to_decimal(value).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def qty(value: Numberish) -> Decimal:
    """Round a quantity to 3 decimals (grams when the base unit is kg)."""
    return to_decimal(value).quantize(QTY_PLACES, rounding=ROUND_HALF_UP)


def unit_cost(value: Numberish) -> Decimal:
    """Cost per base unit keeps 4 decimals so per-kg costs of steel stay accurate."""
    return to_decimal(value).quantize(UNIT_COST_PLACES, rounding=ROUND_HALF_UP)


def round_off(total: Numberish) -> tuple[Decimal, Decimal]:
    """Round an invoice total to the nearest rupee. Returns (rounded_total, round_off_line)."""
    exact = money(total)
    rounded = exact.quantize(RUPEE, rounding=ROUND_HALF_UP)
    return money(rounded), money(rounded - exact)


def split_pro_rata(total: Numberish, weights: list[Decimal]) -> list[Decimal]:
    """Split `total` over `weights` to paise so the parts add up to the total exactly.

    Each part is rounded down to paise, then the paise left over go one each to the parts with
    the largest fractional remainders (earlier part first when tied)."""
    if not weights or any(w < ZERO for w in weights) or sum(weights, ZERO) <= ZERO:
        raise ValueError("weights must be positive and add up to more than zero")
    amount = money(total)
    paise = int(amount * 100)
    whole = sum(weights, ZERO)
    shares = [Decimal(paise) * w / whole for w in weights]
    base = [int(s.to_integral_value(rounding="ROUND_FLOOR")) for s in shares]
    # Rounding down always leaves 0 or more paise over, for negative totals too.
    left = paise - sum(base)
    order = sorted(range(len(weights)), key=lambda i: (-(shares[i] - base[i]), i))
    for i in order[:left]:
        base[i] += 1
    return [Decimal(b) / 100 for b in base]
