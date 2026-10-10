"""Receivables by due date, and bad-debt write-offs (FM5)."""

from datetime import date
from decimal import Decimal

from pydantic import Field

from app.schemas.common import Schema


class BucketsOut(Schema):
    """An amount (or a percentage) for each overdue bucket, counted from the due date."""

    current: Decimal  # not yet due
    days_1_15: Decimal
    days_16_30: Decimal
    days_31_60: Decimal
    over_60: Decimal


class ReceivableRowOut(Schema):
    party_id: int
    party_name: str
    balance: Decimal
    advance: Decimal  # money paid beyond the bills
    overdue: Decimal  # past the due date
    buckets: BucketsOut
    oldest_due_date: date | None  # of the oldest unpaid bill
    days_late: int | None  # of that bill
    credit_limit: Decimal | None  # None: the customer is not on credit
    utilisation_pct: Decimal | None
    dso_days: Decimal | None  # over the last 90 days; None with no credit sales in them
    last_payment_date: date | None


class ReceivablesOut(Schema):
    as_of: date
    total: Decimal  # what customers owe, before any advances
    advances: Decimal
    overdue: Decimal
    buckets: BucketsOut
    rows: list[ReceivableRowOut]


class ReceivablesOwnerOut(ReceivablesOut):
    provision: Decimal  # set aside for doubtful debts: a report, not a booking
    provision_pct: BucketsOut


class WriteoffCreate(Schema):
    location_id: int
    party_id: int
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    reason: str = Field(min_length=3, max_length=200)


class WriteoffOut(Schema):
    id: int
    number: str
    location_id: int
    party_id: int
    party_name: str
    writeoff_date: date
    amount: Decimal
    balance_before: Decimal
    reason: str
    created_by_name: str | None
