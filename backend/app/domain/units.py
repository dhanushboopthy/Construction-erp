"""Unit conversion. Each item has one base unit; other units convert with a fixed factor.

Examples (set per item at setup, never hard-coded):
    TMT bar  base kg   1 ton = 1000 kg; 1 piece of 12 mm x 12 m = theoretical kg per piece
    Cement   base bag  (sold and stocked in bags; 1 bag = 50 kg if weight is ever needed)
    Wire     base kg
"""

from dataclasses import dataclass
from decimal import Decimal

from app.domain.money import ZERO, Numberish, qty, to_decimal


@dataclass(frozen=True)
class UnitConversion:
    unit: str
    factor_to_base: Decimal  # how many base units one of this unit holds
    whole_only: bool = False  # bags and pieces cannot be sold in fractions

    def __post_init__(self) -> None:
        if self.factor_to_base <= ZERO:
            raise ValueError("conversion factor must be positive")


def to_base(quantity: Numberish, conversion: UnitConversion) -> Decimal:
    value = to_decimal(quantity)
    if conversion.whole_only and value != value.to_integral_value():
        raise ValueError(f"{conversion.unit} must be a whole number")
    return qty(value * conversion.factor_to_base)


def from_base(base_quantity: Numberish, conversion: UnitConversion) -> Decimal:
    return qty(to_decimal(base_quantity) / conversion.factor_to_base)
