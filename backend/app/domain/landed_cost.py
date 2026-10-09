"""Landed cost of a purchase line (rules B1, B2 and gap fix G1 in docs/SPEC.md).

    unit_cost = (billed_qty x rate + charges [+ GST only if not claimable]) / received_qty

GST is left out of cost by default: a GST-registered shop claims it back as input tax credit
and charges output GST on the sale, so adding it to cost would count the tax twice. The
`include_gst_in_cost` setting exists for shops that cannot claim it.

Dividing by the received quantity (from the weighbridge slip) means a shortage raises the
unit cost instead of hiding inside the stock value.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from app.domain.money import ZERO, money, to_decimal, unit_cost


class ChargeBasis(StrEnum):
    PER_TON = "per_ton"  # e.g. unloading Rs 250 per ton
    PER_BASE_UNIT = "per_base_unit"  # e.g. unloading per cement bag
    PER_TRIP = "per_trip"  # e.g. transport rent for the truck
    FLAT = "flat"  # e.g. weighbridge Rs 150 per weighing


@dataclass(frozen=True)
class Charge:
    name: str
    basis: ChargeBasis
    amount: Decimal

    def __post_init__(self) -> None:
        if self.amount < ZERO:
            raise ValueError(f"charge {self.name!r} cannot be negative")


@dataclass(frozen=True)
class PurchaseLine:
    billed_qty: Decimal  # base units on the supplier bill
    received_qty: Decimal  # base units actually received (weighbridge)
    rate: Decimal  # per base unit, excluding GST
    gst_rate: Decimal  # percent, e.g. 18
    received_weight_tons: Decimal = ZERO  # needed only for PER_TON charges
    charges: list[Charge] = field(default_factory=list)


@dataclass(frozen=True)
class LandedCost:
    goods_value: Decimal
    gst: Decimal
    charges_total: Decimal
    total_cost: Decimal
    unit_cost: Decimal
    gst_in_cost: bool


def charge_amount(charge: Charge, line: PurchaseLine) -> Decimal:
    match charge.basis:
        case ChargeBasis.PER_TON:
            if line.received_weight_tons <= ZERO:
                raise ValueError(f"{charge.name!r} is per ton but the received weight is missing")
            return money(charge.amount * line.received_weight_tons)
        case ChargeBasis.PER_BASE_UNIT:
            return money(charge.amount * line.received_qty)
        case ChargeBasis.PER_TRIP | ChargeBasis.FLAT:
            return money(charge.amount)


def landed_cost(line: PurchaseLine, include_gst_in_cost: bool = False) -> LandedCost:
    received = to_decimal(line.received_qty)
    if received <= ZERO:
        raise ValueError("received quantity must be positive")
    if to_decimal(line.billed_qty) <= ZERO:
        raise ValueError("billed quantity must be positive")

    goods_value = money(to_decimal(line.billed_qty) * to_decimal(line.rate))
    gst = money(goods_value * to_decimal(line.gst_rate) / 100)
    charges_total = money(sum((charge_amount(c, line) for c in line.charges), ZERO))
    total = goods_value + charges_total + (gst if include_gst_in_cost else ZERO)
    return LandedCost(
        goods_value=goods_value,
        gst=gst,
        charges_total=charges_total,
        total_cost=money(total),
        unit_cost=unit_cost(total / received),
        gst_in_cost=include_gst_in_cost,
    )
