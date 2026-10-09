from datetime import date
from decimal import Decimal
from typing import Annotated, Self

from pydantic import Field, ValidationInfo, field_validator, model_validator

from app.domain.landed_cost import ChargeBasis
from app.models.enums import PaymentDirection, PaymentMode, PurchaseMode, PurchaseStatus
from app.schemas.common import Schema

Qty = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]
Rate = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=4)]
Amount = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
Percent = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]


class CostComponentIn(Schema):
    name: str = Field(min_length=1, max_length=60)
    basis: ChargeBasis
    default_amount: Amount = Decimal("0")


class CostComponentUpdate(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    basis: ChargeBasis | None = None
    default_amount: Amount | None = None
    is_active: bool | None = None


class CostComponentOut(CostComponentIn):
    id: int
    is_active: bool


class ChargeIn(Schema):
    """A charge on one purchase line. Pick a component, or give a name and basis."""

    component_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=60)
    basis: ChargeBasis | None = None
    amount: Amount
    on_supplier_bill: bool = False

    @model_validator(mode="after")
    def _identified(self) -> Self:
        if self.component_id is None and (self.name is None or self.basis is None):
            raise ValueError("Pick a charge type, or give a name and how it is charged")
        return self


class PurchaseLineIn(Schema):
    item_id: int
    unit: str = Field(min_length=1, max_length=16)
    quantity: Qty
    received_quantity: Qty | None = None
    rate: Rate
    gst_rate: Percent | None = None
    charges: list[ChargeIn] = Field(default_factory=list)


class PurchaseCreate(Schema):
    supplier_id: int
    location_id: int
    bill_no: str = Field(min_length=1, max_length=40)
    bill_date: date
    due_date: date | None = None
    mode: PurchaseMode = PurchaseMode.STOCK
    note: str | None = Field(default=None, max_length=500)
    lines: list[PurchaseLineIn] = Field(min_length=1, max_length=100)

    @field_validator("due_date")
    @classmethod
    def _due_after_bill(cls, value: date | None, info: ValidationInfo) -> date | None:
        bill_date = info.data.get("bill_date")
        if value and bill_date and value < bill_date:
            raise ValueError("The due date cannot be before the bill date")
        return value


# ------------------------------------------------------------------ responses


class PurchaseLineOut(Schema):
    """What counter staff and the accountant see: quantities, no money (rule B4)."""

    id: int
    line_no: int
    item_id: int
    item_name: str
    unit: str
    quantity: Decimal
    received_quantity: Decimal
    billed_qty: Decimal
    received_qty: Decimal
    base_unit: str


class PurchaseCostOut(Schema):
    id: int
    component_id: int | None
    name: str
    basis: ChargeBasis
    rate: Decimal
    total: Decimal
    on_supplier_bill: bool


class PurchaseLineOwnerOut(PurchaseLineOut):
    rate: Decimal
    gst_rate: Decimal
    goods_value: Decimal
    gst_amount: Decimal
    charges_total: Decimal
    total_cost: Decimal
    unit_cost: Decimal
    costs: list[PurchaseCostOut]


class PurchaseOut(Schema):
    id: int
    number: str
    supplier_id: int
    supplier_name: str
    location_id: int
    location_code: str
    bill_no: str
    bill_date: date
    due_date: date | None
    mode: PurchaseMode
    status: PurchaseStatus
    note: str | None
    lines: list[PurchaseLineOut]


class PurchaseOwnerOut(PurchaseOut):
    goods_value: Decimal
    gst_amount: Decimal
    charges_total: Decimal
    supplier_payable: Decimal
    lines: list[PurchaseLineOwnerOut]  # type: ignore[assignment]


class PreviewLine(Schema):
    item_id: int
    item_name: str
    base_unit: str
    billed_qty: Decimal
    received_qty: Decimal
    goods_value: Decimal
    gst_amount: Decimal
    charges_total: Decimal
    total_cost: Decimal
    unit_cost: Decimal
    costs: list[PurchaseCostOut]


class PurchasePreview(Schema):
    goods_value: Decimal
    gst_amount: Decimal
    charges_total: Decimal
    supplier_payable: Decimal
    gst_in_cost: bool
    lines: list[PreviewLine]


# ------------------------------------------------------------------ payments


class AllocationIn(Schema):
    """Aim part of a payment at one bill (its number). Blank allocations mean oldest first."""

    bill_no: str = Field(min_length=1, max_length=20)
    amount: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]


class AllocationOut(Schema):
    bill_no: str
    amount: Decimal


class PaymentCreate(Schema):
    direction: PaymentDirection = PaymentDirection.PAID
    party_id: int
    site_id: int | None = None
    location_id: int
    amount: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]
    mode: PaymentMode
    reference: str | None = Field(default=None, max_length=60)
    payment_date: date
    note: str | None = Field(default=None, max_length=200)
    allocations: list[AllocationIn] = Field(default_factory=list)


class PaymentOut(Schema):
    id: int
    number: str
    direction: PaymentDirection
    party_id: int
    party_name: str
    location_id: int
    amount: Decimal
    mode: PaymentMode
    reference: str | None
    payment_date: date
    note: str | None
    site_id: int | None = None
    applied: list[AllocationOut] = Field(default_factory=list)
    advance: Decimal = Decimal("0")
