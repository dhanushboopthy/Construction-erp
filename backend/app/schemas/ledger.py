from datetime import date
from decimal import Decimal

from app.models.enums import LedgerAccount, PartyRef
from app.schemas.common import Schema


class LedgerLineOut(Schema):
    id: int
    entry_date: date
    ref_type: PartyRef
    doc_no: str | None
    site_id: int | None
    debit: Decimal
    credit: Decimal
    running_balance: Decimal
    narration: str | None


class AgingOut(Schema):
    up_to_30: Decimal
    days_31_60: Decimal
    over_60: Decimal


class AccountOut(Schema):
    account: LedgerAccount
    balance: Decimal
    advance: Decimal
    aging: AgingOut
    entries: list[LedgerLineOut]


class StatementOut(Schema):
    party_id: int
    party_name: str
    site_id: int | None
    receivable: AccountOut | None
    payable: AccountOut | None


class DuesRowOut(Schema):
    party_id: int
    party_name: str
    balance: Decimal
    advance: Decimal
    aging: AgingOut
    oldest_date: date | None


class DuesOut(Schema):
    account: LedgerAccount
    as_of: date
    total: Decimal
    rows: list[DuesRowOut]


class OpenBillOut(Schema):
    bill_no: str
    bill_date: date
    due_date: date | None
    original: Decimal
    remaining: Decimal
    overdue: bool


class OpenBillsOut(Schema):
    party_id: int
    account: LedgerAccount
    bills: list[OpenBillOut]
    advance: Decimal
