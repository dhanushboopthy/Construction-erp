"""Tally export (FM4): ledger names, the preview and its reconciliation checks."""

from datetime import date
from decimal import Decimal

from pydantic import Field

from app.schemas.common import Schema


class TallyLedgerOut(Schema):
    purpose: str
    label: str  # what the ledger is for, in plain words
    name: str  # the name used in the export
    default: str
    group: str  # the Tally group it is created under
    is_custom: bool


class TallyLedgersOut(Schema):
    company: str  # the Tally company name the file imports into
    default_company: str
    ledgers: list[TallyLedgerOut]


class TallyLedgersPut(Schema):
    """Names the accountant uses in Tally. A blank name goes back to the default."""

    company: str | None = Field(default=None, max_length=100)
    names: dict[str, str] = Field(default_factory=dict)


class TallyKindOut(Schema):
    kind: str
    count: int
    total: Decimal  # sum of the debits of these vouchers


class TallyCheckOut(Schema):
    code: str
    label: str
    vouchers: Decimal  # what the exported vouchers add up to
    report: Decimal  # what the report shows for the same period
    ok: bool


class TallyPreviewOut(Schema):
    date_from: date
    date_to: date
    company: str
    voucher_count: int
    kinds: list[TallyKindOut]
    checks: list[TallyCheckOut]
    gst_checked: bool  # False when the range is not whole calendar months
    note: str | None
