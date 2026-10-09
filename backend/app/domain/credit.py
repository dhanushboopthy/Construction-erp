"""Customer credit control (rule B8).

Credit is for approved customers only. A credit sale is blocked (owner can override) when:
  - the customer is not allowed credit,
  - outstanding + the unpaid part of this bill would exceed the limit, or
  - any unpaid invoice is past its due date (invoice date + credit days).
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from app.domain.money import ZERO, Numberish, money, to_decimal


class CreditViolation(StrEnum):
    CREDIT_NOT_ALLOWED = "CREDIT_NOT_ALLOWED"
    CREDIT_LIMIT_EXCEEDED = "CREDIT_LIMIT_EXCEEDED"
    OVERDUE_INVOICES = "OVERDUE_INVOICES"


@dataclass(frozen=True)
class CreditPolicy:
    credit_allowed: bool
    limit: Decimal
    days: int


@dataclass(frozen=True)
class OpenInvoice:
    number: str
    invoice_date: date
    due_date: date
    balance: Decimal


@dataclass(frozen=True)
class CreditDecision:
    outstanding: Decimal
    available: Decimal
    violations: list[CreditViolation] = field(default_factory=list)
    overdue: list[str] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return not self.violations


def due_date(invoice_date: date, credit_days: int) -> date:
    return invoice_date + timedelta(days=credit_days)


def check_credit(
    policy: CreditPolicy,
    open_invoices: list[OpenInvoice],
    unpaid_amount: Numberish,
    today: date,
) -> CreditDecision:
    """`unpaid_amount` is what this bill leaves unpaid (total minus cash/UPI taken now)."""
    outstanding = money(sum((inv.balance for inv in open_invoices if inv.balance > ZERO), ZERO))
    available = money(max(policy.limit - outstanding, ZERO))
    new_credit = money(to_decimal(unpaid_amount))
    if new_credit <= ZERO:
        return CreditDecision(outstanding, available)

    violations: list[CreditViolation] = []
    if not policy.credit_allowed:
        violations.append(CreditViolation.CREDIT_NOT_ALLOWED)
    if outstanding + new_credit > policy.limit:
        violations.append(CreditViolation.CREDIT_LIMIT_EXCEEDED)
    overdue = [inv.number for inv in open_invoices if inv.balance > ZERO and inv.due_date < today]
    if overdue:
        violations.append(CreditViolation.OVERDUE_INVOICES)
    return CreditDecision(outstanding, available, violations, overdue)
