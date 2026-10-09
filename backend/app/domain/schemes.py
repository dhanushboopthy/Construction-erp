"""Supplier target schemes (Milestone 11, rule B15): buy a volume in a period, earn a rebate."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from app.domain.money import ZERO, Numberish, money, qty, to_decimal

ALERT_AT_PCT = Decimal("80")


class RebateRule(StrEnum):
    PERCENT = "percent"  # % of the goods value of qualifying purchases
    PER_UNIT = "per_unit"  # rupees for each base unit bought
    FLAT = "flat"  # one fixed amount once the target is met


@dataclass(frozen=True)
class Progress:
    target: Decimal
    achieved: Decimal
    pct: Decimal
    remaining: Decimal
    reached: bool
    alert: bool  # 80% or more of the target, and the target not yet met


def progress(target: Numberish, achieved: Numberish) -> Progress:
    tgt, got = to_decimal(target), to_decimal(achieved)
    if tgt <= ZERO:
        raise ValueError("the target must be positive")
    if got < ZERO:
        raise ValueError("the volume bought cannot be negative")
    reached = got >= tgt
    # The alert is decided on the exact figures, not the rounded percentage shown.
    alert = not reached and got * 100 >= ALERT_AT_PCT * tgt
    return Progress(
        target=qty(tgt),
        achieved=qty(got),
        pct=(got / tgt * 100).quantize(Decimal("0.01")),
        remaining=qty(max(tgt - got, ZERO)),
        reached=reached,
        alert=alert,
    )


def rebate_amount(
    rule: RebateRule, value: Numberish, qualifying_value: Numberish, qualifying_qty: Numberish
) -> Decimal:
    rate = to_decimal(value)
    if rate < ZERO:
        raise ValueError("the rebate cannot be negative")
    if rule is RebateRule.PERCENT:
        return money(to_decimal(qualifying_value) * rate / 100)
    if rule is RebateRule.PER_UNIT:
        return money(to_decimal(qualifying_qty) * rate)
    return money(rate)


def in_period(on: date, start: date, end: date) -> bool:
    return start <= on <= end
