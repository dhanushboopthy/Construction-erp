from datetime import date
from decimal import Decimal

from pydantic import Field

from app.domain.gst import SupplyKind
from app.models.enums import SupplyType
from app.schemas.common import Schema


class ReturnLineIn(Schema):
    line_id: int  # the sales line (credit note) or purchase line (debit note) being returned
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)  # in the unit of that line


class CreditNoteCreate(Schema):
    invoice_id: int
    reason: str = Field(min_length=3, max_length=300)
    lines: list[ReturnLineIn] = Field(min_length=1, max_length=100)
    approval_ids: list[int] = Field(default_factory=list, max_length=10)


class DebitNoteCreate(Schema):
    purchase_id: int
    reason: str = Field(min_length=3, max_length=300)
    lines: list[ReturnLineIn] = Field(min_length=1, max_length=100)


class NoteLineOut(Schema):
    id: int
    line_no: int
    item_id: int
    description: str
    hsn: str
    base_qty: Decimal
    base_unit: str
    taxable: Decimal
    gst_rate: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    line_total: Decimal


class CreditNoteLineOut(NoteLineOut):
    sales_line_id: int
    rate: Decimal
    restocked_at: int | None


class DebitNoteLineOut(NoteLineOut):
    purchase_line_id: int


class NoteSummary(Schema):
    id: int
    number: str
    note_date: date
    party_id: int
    party_name: str
    location_id: int
    location_code: str
    reason: str
    grand_total: Decimal


class CreditNoteSummary(NoteSummary):
    invoice_id: int
    invoice_number: str


class DebitNoteSummary(NoteSummary):
    purchase_id: int
    purchase_number: str
    supplier_bill_no: str


class CreditNoteOut(CreditNoteSummary):
    financial_year: str
    site_id: int | None
    bill_to_gstin: str | None
    place_of_supply: str
    supply_kind: SupplyKind
    supply_type: SupplyType
    taxable_value: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    round_off: Decimal
    approved_by: int | None
    lines: list[CreditNoteLineOut]


class DebitNoteOut(DebitNoteSummary):
    financial_year: str
    supply_kind: SupplyKind
    taxable_value: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    round_off: Decimal
    lines: list[DebitNoteLineOut]
