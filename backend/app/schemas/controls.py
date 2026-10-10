"""Controls (FM7): the period lock, bank statements and the exception report."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from app.schemas.common import Schema

# ---------------------------------------------------------------------------- period lock


class PeriodLockOut(Schema):
    locked_through: date | None
    changed_at: datetime | None = None
    changed_by_name: str | None = None
    reason: str | None = None


class PeriodLockSet(Schema):
    """`locked_through` of null removes the lock."""

    locked_through: date | None
    reason: str = Field(min_length=5, max_length=200)


class ChecklistItem(Schema):
    code: str
    label: str
    state: str  # ok | warn
    detail: str


class PeriodChecklist(Schema):
    period: str
    items: list[ChecklistItem]
    ready: bool  # nothing needs a look before the month is locked


# ---------------------------------------------------------------------------- bank


class BankAccountCreate(Schema):
    name: str = Field(min_length=1, max_length=60)
    account_no_last4: str | None = Field(default=None, pattern=r"^[0-9]{4}$")


class BankAccountUpdate(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    is_active: bool | None = None


class BankAccountOut(Schema):
    id: int
    name: str
    account_no_last4: str | None
    is_active: bool


class BankStatementOut(Schema):
    id: int
    bank_account_id: int
    bank_account_name: str
    filename: str
    from_date: date
    to_date: date
    row_count: int
    skipped_count: int  # rows already imported from an overlapping file
    closing_balance: Decimal | None
    imported_at: datetime
    imported_by_name: str | None


class BankLineOut(Schema):
    id: int
    line_date: date
    narration: str
    reference: str
    debit: Decimal
    credit: Decimal
    matched: bool
    matched_key: str | None = None
    matched_label: str | None = None
    matched_how: str | None = None  # reference | amount


class BookEntryOut(Schema):
    key: str
    entry_date: date
    label: str
    mode: str
    reference: str | None
    amount: Decimal
    money_in: bool


class ReconciliationOut(Schema):
    date_from: date
    date_to: date
    window_days: int
    lines: list[BankLineOut]
    line_count: int
    matched_count: int
    unmatched_count: int
    unmatched_in: Decimal  # money the bank shows that the books do not
    unmatched_out: Decimal
    not_in_bank: list[BookEntryOut]  # recorded as paid or received, not on the statement
    not_in_bank_total: Decimal
    last_balance: Decimal | None  # the latest balance on any statement in range
    last_balance_date: date | None


# ---------------------------------------------------------------------------- exceptions


class ExceptionRow(Schema):
    code: str
    title: str
    on: date
    location_code: str | None
    user_name: str | None
    document: str | None
    detail: str
    value: Decimal | None  # owner only report: rupees involved when there is one
    link: str | None = None  # an app path for the drill-down


class ExceptionCount(Schema):
    code: str
    title: str
    count: int


class ExceptionReport(Schema):
    date_from: date
    date_to: date
    rows: list[ExceptionRow]
    counts: list[ExceptionCount]
