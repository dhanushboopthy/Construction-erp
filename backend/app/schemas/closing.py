from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from app.models.enums import ClosingStatus
from app.schemas.common import Schema


class ModeTotals(Schema):
    cash: Decimal
    upi: Decimal
    bank: Decimal
    total: Decimal


class TopItem(Schema):
    description: str
    base_unit: str
    quantity: Decimal
    taxable: Decimal


class ClosingFigures(Schema):
    """The day's numbers for one shop. No cost, margin or profit: staff close their own day."""

    location_id: int
    location_code: str
    closing_date: date
    invoices_count: int
    first_invoice: str | None
    last_invoice: str | None
    taxable: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    round_off: Decimal
    sales_total: Decimal
    credit_given: Decimal  # billed today and not paid with the bill
    returns_count: int
    returns_total: Decimal
    receipts: ModeTotals
    cash_out: Decimal
    purchases_count: int
    top_items: list[TopItem]


class ClosingCreate(Schema):
    location_id: int
    closing_date: date
    counted_cash: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    opening_cash: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    note: str | None = Field(default=None, max_length=300)


class ReopenIn(Schema):
    reason: str = Field(min_length=3, max_length=300)


class ClosingOut(Schema):
    id: int
    location_id: int
    location_code: str
    closing_date: date
    status: ClosingStatus
    invoices_count: int
    sales_total: Decimal
    returns_total: Decimal
    opening_cash: Decimal
    cash_in: Decimal
    cash_out: Decimal
    expected_cash: Decimal
    counted_cash: Decimal
    difference: Decimal
    note: str | None
    closed_at: datetime | None
    reopened_at: datetime | None
    reopen_reason: str | None
    times_closed: int
    has_pdf: bool


class ClosingPreview(Schema):
    figures: ClosingFigures
    opening_cash: Decimal  # last closing's counted cash, else 0
    expected_cash: Decimal
    existing: ClosingOut | None
    locked: bool
    profit: Decimal | None = None  # owner only
