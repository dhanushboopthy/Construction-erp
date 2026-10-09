"""Selling price resolution and margin checks (rules B3, B5).

Order: an active customer-specific rate, else the latest daily market rate on or before the
bill date. No rate at all blocks the line; staff never type their own price.
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from app.domain.money import ZERO, Numberish, money, to_decimal, unit_cost


class RateSource(StrEnum):
    CUSTOMER = "customer"
    MARKET = "market"


class PriceNotSetError(LookupError):
    pass


@dataclass(frozen=True)
class CustomerRate:
    rate: Decimal
    valid_from: date
    valid_to: date | None = None

    def active_on(self, on: date) -> bool:
        return self.valid_from <= on and (self.valid_to is None or on <= self.valid_to)


@dataclass(frozen=True)
class MarketRate:
    rate: Decimal
    effective_date: date


@dataclass(frozen=True)
class ResolvedPrice:
    rate: Decimal
    source: RateSource


def resolve_price(
    on: date, customer_rates: list[CustomerRate], market_rates: list[MarketRate]
) -> ResolvedPrice:
    active = [r for r in customer_rates if r.active_on(on)]
    if active:
        best = max(active, key=lambda r: r.valid_from)
        return ResolvedPrice(best.rate, RateSource.CUSTOMER)
    known = [r for r in market_rates if r.effective_date <= on]
    if known:
        latest = max(known, key=lambda r: r.effective_date)
        return ResolvedPrice(latest.rate, RateSource.MARKET)
    raise PriceNotSetError("No market rate set for this item. Ask the owner to enter today's rate.")


def suggested_price(cost: Numberish, margin_per_unit: Numberish) -> Decimal:
    """What the daily rate screen proposes to the owner: landed cost + margin."""
    return money(to_decimal(cost) + to_decimal(margin_per_unit))


@dataclass(frozen=True)
class MarginCheck:
    margin_per_unit: Decimal
    below_cost: bool  # blocks: needs owner approval (B5)
    below_min_margin: bool  # warns the owner only


def check_margin(rate: Numberish, cost: Numberish, min_margin: Numberish = 0) -> MarginCheck:
    margin = unit_cost(to_decimal(rate) - to_decimal(cost))
    return MarginCheck(
        margin_per_unit=margin,
        below_cost=margin < ZERO,
        below_min_margin=margin < to_decimal(min_margin),
    )


RATE_PLACES = Decimal("0.000001")


def _rate(value: Numberish) -> Decimal:
    rate = to_decimal(value)
    if rate < ZERO:
        raise ValueError("a rate cannot be negative")
    return rate


def exclusive_rate(entered: Numberish, gst_rate: Numberish, *, includes_gst: bool) -> Decimal:
    """Selling rates are stored without GST (G2). If the owner quotes rates with tax included,
    back the tax out: exclusive = inclusive x 100 / (100 + GST rate). Kept to 6 places so a bill
    (quantity x rate, rounded once to paise) matches a calculator."""
    rate = _rate(entered)
    if includes_gst:
        rate = rate * 100 / (100 + to_decimal(gst_rate))
    return rate.quantize(RATE_PLACES, rounding=ROUND_HALF_UP)


def rate_per_base_unit(rate: Numberish, factor_to_base: Numberish) -> Decimal:
    """Convert a rate quoted per ton or per bundle to a rate per base unit (kg, bag, piece)."""
    factor = to_decimal(factor_to_base)
    if factor <= ZERO:
        raise ValueError("unit factor must be positive")
    return (_rate(rate) / factor).quantize(RATE_PLACES, rounding=ROUND_HALF_UP)


def margin_per_base_unit(margin: Numberish, factor_to_base: Numberish) -> Decimal:
    """The owner thinks of margin per ton (Rs 1,000-1,500); prices are per kg. Convert."""
    return rate_per_base_unit(margin, factor_to_base)
