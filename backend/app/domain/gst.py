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
_PAN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
_CIN = re.compile(r"^[LU][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$")


STATE_NAMES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh",
    "05": "Uttarakhand", "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur",
    "15": "Mizoram", "16": "Tripura", "17": "Meghalaya", "18": "Assam", "19": "West Bengal",
    "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh",
    "24": "Gujarat", "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra",
    "29": "Karnataka", "30": "Goa", "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu",
    "34": "Puducherry", "35": "Andaman and Nicobar Islands", "36": "Telangana",
    "37": "Andhra Pradesh", "38": "Ladakh", "97": "Other territory",
}  # fmt: skip


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


def is_valid_pan(pan: str) -> bool:
    """Five letters, four digits, one letter."""
    return bool(_PAN.match(pan.strip().upper()))


def is_valid_cin(cin: str) -> bool:
    """The registrar's 21 characters: listed (L) or unlisted (U), industry code, state, year,
    ownership type and a serial number. The layout is checked, not the registry."""
    return bool(_CIN.match(cin.strip().upper()))


def pan_of(gstin: str | None) -> str | None:
    """Characters 3 to 12 of a GSTIN are the holder's PAN."""
    return gstin[2:12] if gstin else None


@dataclass(frozen=True)
class HsnTax:
    hsn: str
    rate: Decimal
    taxable: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal

    @property
    def tax(self) -> Decimal:
        return self.cgst + self.sgst + self.igst


def hsn_summary(lines: list[tuple[str, LineTax]]) -> list[HsnTax]:
    """The bill's tax per HSN and rate, in the order each first appears. Sums the tax already
    rounded on each line, so the summary always adds up to the bill."""
    groups: dict[tuple[str, Decimal], list[LineTax]] = {}
    for hsn, tax in lines:
        groups.setdefault((hsn, tax.rate), []).append(tax)
    return [
        HsnTax(
            hsn=hsn,
            rate=rate,
            taxable=sum((x.taxable for x in taxes), ZERO),
            cgst=sum((x.cgst for x in taxes), ZERO),
            sgst=sum((x.sgst for x in taxes), ZERO),
            igst=sum((x.igst for x in taxes), ZERO),
        )
        for (hsn, rate), taxes in groups.items()
    ]


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
