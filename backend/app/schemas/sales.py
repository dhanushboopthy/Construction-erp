from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import Field

from app.domain.gst import SupplyKind
from app.domain.pricing import RateSource
from app.models.enums import (
    ApprovalAction,
    FulfilmentSource,
    InvoiceStatus,
    PaymentMode,
    SupplyType,
)
from app.schemas.common import Schema

Qty = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]
Amount = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
Rate = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=4)]


class InvoiceLineIn(Schema):
    item_id: int
    quantity: Qty
    unit: str | None = Field(default=None, max_length=16)  # blank: the item's base unit
    source: FulfilmentSource = FulfilmentSource.SHOP
    source_location_id: int | None = None  # for source "godown": which place; blank = shop
    # Owner only (rule B4, G10): counter staff ask the owner instead.
    discount: Amount | None = None
    discount_reason: str | None = Field(default=None, max_length=200)
    rate_override: Rate | None = None  # per `unit`


class BillPaymentIn(Schema):
    """Money taken at the counter with the bill (cash, UPI or bank; no cheques, B7)."""

    mode: PaymentMode
    amount: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]
    reference: str | None = Field(default=None, max_length=60)


class InvoiceCreate(Schema):
    location_id: int
    party_id: int
    site_id: int | None = None
    invoice_date: date | None = None
    vehicle_no: str | None = Field(default=None, max_length=20)
    remark: str | None = Field(default=None, max_length=300)
    lines: list[InvoiceLineIn] = Field(min_length=1, max_length=100)
    payments: list[BillPaymentIn] = Field(default_factory=list)
    # Owner PIN approvals obtained for this bill (POST /approvals, G18).
    approval_ids: list[int] = Field(default_factory=list, max_length=10)


# ------------------------------------------------------------------ preview


class PreviewLineOut(Schema):
    item_id: int
    description: str
    unit: str
    quantity: Decimal
    base_qty: Decimal
    base_unit: str
    rate: Decimal | None
    rate_source: RateSource | None
    discount: Decimal
    taxable: Decimal
    gst_rate: Decimal
    tax: Decimal
    line_total: Decimal
    fulfilment_source: FulfilmentSource
    stock_available: Decimal | None
    stock_after: Decimal | None
    problems: list[str]


class InvoicePreview(Schema):
    place_of_supply: str
    supply_kind: SupplyKind
    supply_type: SupplyType
    pending_balance: Decimal
    taxable_value: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    round_off: Decimal
    grand_total: Decimal
    paid_now: Decimal
    balance_due: Decimal
    invoice_problems: list[str]
    needs_owner: bool  # a problem the owner's PIN can clear
    approvals_needed: list[ApprovalAction]  # which approvals to ask the owner for
    lines: list[PreviewLineOut]
    can_save: bool


# ------------------------------------------------------------------ saved invoices


class InvoiceLineOut(Schema):
    id: int
    line_no: int
    item_id: int
    description: str
    hsn: str
    unit: str
    quantity: Decimal
    base_qty: Decimal
    base_unit: str
    rate: Decimal
    rate_source: RateSource
    discount: Decimal
    discount_reason: str | None
    taxable: Decimal
    gst_rate: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    line_total: Decimal
    fulfilment_source: FulfilmentSource
    source_location_id: int | None
    stock_after: Decimal | None
    returned_qty: Decimal = Decimal("0")  # taken back by credit notes so far


class InvoiceLineOwnerOut(InvoiceLineOut):
    cost_per_unit: Decimal
    profit: Decimal


class InvoiceSummary(Schema):
    id: int
    number: str
    invoice_date: date
    party_id: int
    party_name: str
    location_id: int
    location_code: str
    supply_type: SupplyType
    grand_total: Decimal
    status: InvoiceStatus


class InvoiceOut(InvoiceSummary):
    financial_year: str
    site_id: int | None
    bill_to_name: str
    bill_to_address: str
    bill_to_gstin: str | None
    ship_to_name: str | None
    ship_to_address: str | None
    ship_to_gstin: str | None
    place_of_supply: str
    supply_kind: SupplyKind
    due_date: date | None
    taxable_value: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    round_off: Decimal
    pending_balance_at_billing: Decimal
    paid_at_billing: Decimal
    vehicle_no: str | None
    remark: str | None
    lines: list[InvoiceLineOut]


class InvoiceOwnerOut(InvoiceOut):
    profit: Decimal
    lines: list[InvoiceLineOwnerOut]  # type: ignore[assignment]
