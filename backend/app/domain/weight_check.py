"""Weight fail-check (rule B14): billed vs weighbridge weight, flagged above a threshold."""

from dataclasses import dataclass
from decimal import Decimal

from app.domain.money import ZERO, Numberish, money, qty, to_decimal


@dataclass(frozen=True)
class WeightCheck:
    expected: Decimal
    actual: Decimal
    difference: Decimal  # actual - expected; negative means short
    variance_pct: Decimal
    flagged: bool

    def shortage_value(self, cost_per_unit: Numberish) -> Decimal:
        """Rupee value of a shortage (0 when nothing is short)."""
        short = max(-self.difference, ZERO)
        return money(short * to_decimal(cost_per_unit))


def check_weight(expected: Numberish, actual: Numberish, threshold_pct: Numberish) -> WeightCheck:
    exp, act, limit = to_decimal(expected), to_decimal(actual), to_decimal(threshold_pct)
    if exp <= ZERO:
        raise ValueError("expected weight must be positive")
    if act < ZERO:
        raise ValueError("actual weight cannot be negative")
    diff = act - exp
    pct = (abs(diff) / exp * 100).quantize(Decimal("0.01"))
    return WeightCheck(qty(exp), qty(act), qty(diff), pct, flagged=pct > limit)
