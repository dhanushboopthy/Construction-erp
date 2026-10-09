"""Small compliance checks. Thresholds come from shop settings because they change by state
and over time; confirm current values with the accountant (docs/GAP_ANALYSIS.md)."""

from datetime import date
from decimal import Decimal

from app.domain.money import Numberish, money, to_decimal


def eway_bill_required(
    consignment_value: Numberish,
    inter_state: bool,
    interstate_threshold: Numberish,
    intrastate_threshold: Numberish,
) -> bool:
    """An e-way bill is needed when the consignment value exceeds the applicable threshold."""
    limit = to_decimal(interstate_threshold if inter_state else intrastate_threshold)
    return money(consignment_value) > limit


def cash_receipt_blocked(
    cash_already_received_today: Numberish, new_cash: Numberish, limit: Numberish
) -> bool:
    """Income-tax law bars receiving cash of the limit (Rs 2 lakh) or more from one person in a
    day, for one transaction or one event. Block the receipt and ask for UPI or bank transfer."""
    total: Decimal = money(cash_already_received_today) + money(new_cash)
    return total >= to_decimal(limit)


def return_window_open(invoice_date: date, return_date: date, window_days: int) -> bool:
    """Rule B11: a return within the window goes back to stock without owner approval."""
    age = (return_date - invoice_date).days
    return 0 <= age <= window_days


def freight_cash_warning(
    cash_already_paid_today: Decimal, new_cash: Decimal, daily_limit: Decimal
) -> bool:
    """G14: cash freight above the daily limit to one transporter is not deductible, so warn.
    Exactly the limit is still fine."""
    total: Decimal = money(cash_already_paid_today) + money(new_cash)
    return total > to_decimal(daily_limit)
