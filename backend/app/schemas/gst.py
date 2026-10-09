from datetime import date
from decimal import Decimal
from typing import Literal

from app.schemas.common import Schema


class RateRow(Schema):
    rate: Decimal
    taxable: Decimal
    igst: Decimal
    cgst: Decimal
    sgst: Decimal


class B2bInvoice(Schema):
    ctin: str | None  # buyer GSTIN (none for B2CL)
    party_name: str
    number: str
    invoice_date: date
    value: Decimal
    pos: str
    taxable: Decimal
    igst: Decimal
    cgst: Decimal
    sgst: Decimal
    rates: list[RateRow]


class B2csRow(Schema):
    supply: Literal["INTRA", "INTER"]
    pos: str
    rate: Decimal
    taxable: Decimal
    igst: Decimal
    cgst: Decimal
    sgst: Decimal


class NoteRow(Schema):
    ctin: str | None
    party_name: str
    number: str
    note_date: date
    invoice_number: str
    invoice_date: date
    value: Decimal
    pos: str
    taxable: Decimal
    igst: Decimal
    cgst: Decimal
    sgst: Decimal
    rates: list[RateRow]


class HsnRow(Schema):
    hsn: str
    description: str
    uqc: str
    quantity: Decimal
    rate: Decimal
    value: Decimal
    taxable: Decimal
    igst: Decimal
    cgst: Decimal
    sgst: Decimal


class DocRow(Schema):
    nature: str
    series: str
    first: str
    last: str
    count: int
    gaps: list[int]


class Totals(Schema):
    invoices: int
    notes: int
    taxable: Decimal  # net of credit notes
    igst: Decimal
    cgst: Decimal
    sgst: Decimal


class Gstr1(Schema):
    period: str
    gstin: str | None
    b2b: list[B2bInvoice]
    b2cl: list[B2bInvoice]
    b2cs: list[B2csRow]
    cdnr: list[NoteRow]
    cdnur: list[NoteRow]
    hsn: list[HsnRow]
    docs: list[DocRow]
    totals: Totals


class Heads(Schema):
    taxable: Decimal
    igst: Decimal
    cgst: Decimal
    sgst: Decimal


class Gstr3b(Schema):
    period: str
    gstin: str | None
    outward_taxable: Heads  # 3.1(a): sales at a GST rate, net of credit notes
    outward_nil: Decimal  # 3.1(c): sales at 0%, net of credit notes
    itc_books: Heads  # 4(A): input tax on purchases in the period, per our books
    itc_reversed: Heads  # 4(B): input tax taken back on debit notes
    itc_in_2b: Heads | None  # what the latest GSTR-2B shows for the month, when imported
    net_payable: Heads  # outward tax less (books ITC less reversed), per head (can be negative)


MatchStatus = Literal["matched", "mismatch", "missing_in_2b", "missing_in_books"]


class MatchRow(Schema):
    status: MatchStatus
    gstin: str
    supplier: str | None
    number: str
    books_date: date | None
    books_taxable: Decimal | None
    books_tax: Decimal | None
    portal_taxable: Decimal | None
    portal_tax: Decimal | None
    difference_taxable: Decimal
    difference_tax: Decimal


class Gstr2bResult(Schema):
    period: str
    file_name: str | None
    imported_rows: int
    counts: dict[str, int]
    rows: list[MatchRow]


class ImportOut(Schema):
    id: int
    period: str
    file_name: str
    row_count: int
