"""GST maths: place of supply, CGST+SGST vs IGST split, line tax and invoice totals.

Every rule here should be confirmed with the shop's accountant before go-live; tax rules change.
"""

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.domain.money import ZERO, Numberish, money, round_off, to_decimal

_GSTIN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


class SupplyKind(StrEnum):
    INTRA_STATE = "intra_state"  # CGST + SGST
    INTER_STATE = "inter_state"  # IGST


def gstin_checksum(first14: str) -> str:
    """Check character of a GSTIN (base-36 weighted sum)."""
    total = 0
    for index, char in enumerate(first14):
        product = _GSTIN_CHARS.index(char) * (2 if index % 2 else 1)
        total += product // 36 + product % 36
    return _GSTIN_CHARS[(36 - total % 36) % 36]


def is_valid_gstin(gstin: str) -> bool:
    gstin = gstin.strip().upper()
    return bool(_GSTIN.match(gstin)) and gstin_checksum(gstin[:14]) == gstin[14]


def state_code_of(gstin: str) -> str:
    return gstin.strip()[:2]


def place_of_supply(shop_state: str, ship_to_state: str | None) -> str:
    """Goods delivered to a site: the site's state. Counter pickup: the shop's state."""
    return ship_to_state or shop_state


def supply_kind(supplier_state: str, place_of_supply_state: str) -> SupplyKind:
    if supplier_state == place_of_supply_state:
        return SupplyKind.INTRA_STATE
    return SupplyKind.INTER_STATE


@dataclass(frozen=True)
class LineTax:
    taxable: Decimal
    rate: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal

    @property
    def tax(self) -> Decimal:
        return self.cgst + self.sgst + self.igst

    @property
    def total(self) -> Decimal:
        return self.taxable + self.tax


def taxable_value(quantity: Numberish, rate: Numberish, discount: Numberish = 0) -> Decimal:
    """Discount reduces the taxable value of the line (owner-only, see rule B4)."""
    value = money(to_decimal(quantity) * to_decimal(rate)) - money(discount)
    if value < ZERO:
        raise ValueError("discount cannot exceed the line value")
    return value


def taxable_from_inclusive(amount_incl_tax: Numberish, rate: Numberish) -> Decimal:
    """Back out the taxable value when a rate is quoted inclusive of GST."""
    amount, pct = to_decimal(amount_incl_tax), to_decimal(rate)
    return money(amount * 100 / (100 + pct))


def line_tax(taxable: Numberish, rate: Numberish, kind: SupplyKind) -> LineTax:
    """Tax per line, rounded per line. Intra-state splits the rate in half, so CGST == SGST."""
    value, pct = money(taxable), to_decimal(rate)
    if pct < ZERO:
        raise ValueError("GST rate cannot be negative")
    if kind is SupplyKind.INTRA_STATE:
        half = money(value * pct / 2 / 100)
        return LineTax(value, pct, cgst=half, sgst=half, igst=ZERO)
    return LineTax(value, pct, cgst=ZERO, sgst=ZERO, igst=money(value * pct / 100))


@dataclass(frozen=True)
class InvoiceTotals:
    taxable: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    tax: Decimal
    before_round_off: Decimal
    round_off: Decimal
    grand_total: Decimal


def invoice_totals(lines: list[LineTax]) -> InvoiceTotals:
    taxable = money(sum((line.taxable for line in lines), ZERO))
    cgst = money(sum((line.cgst for line in lines), ZERO))
    sgst = money(sum((line.sgst for line in lines), ZERO))
    igst = money(sum((line.igst for line in lines), ZERO))
    tax = cgst + sgst + igst
    before = taxable + tax
    grand_total, adjustment = round_off(before)
    return InvoiceTotals(taxable, cgst, sgst, igst, tax, before, adjustment, grand_total)
