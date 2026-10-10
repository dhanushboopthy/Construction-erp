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
    # B14: needed when the received weight differs from the billed weight by more than the setting.
    weight_note: str | None = Field(default=None, max_length=300)
    # FM10: the manufacturing week printed on the bags (cement only, optional).
    mfg_week: int | None = Field(default=None, ge=1, le=53)
    mfg_year: int | None = Field(default=None, ge=2000, le=2100)

    @model_validator(mode="after")
    def _week_with_year(self) -> Self:
        if (self.mfg_week is None) != (self.mfg_year is None):
            raise ValueError("Give both the manufacturing week and its year, or neither")
        return self


class PurchaseCreate(Schema):
    supplier_id: int
    location_id: int
    bill_no: str = Field(min_length=1, max_length=40)
    bill_date: date
    due_date: date | None = None
    mode: PurchaseMode = PurchaseMode.STOCK
    note: str | None = Field(default=None, max_length=500)
    lines: list[PurchaseLineIn] = Field(min_length=1, max_length=100)
    # FM10: the purchase order this bill is against, and the owner's approval (po_mismatch) for a
    # bill that does not match it.
    purchase_order_id: int | None = None
    approval_ids: list[int] = Field(default_factory=list, max_length=5)

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
    weight_variance_pct: Decimal = Decimal("0")
    weight_flagged: bool = False
    weight_note: str | None = None
    mfg_week: int | None = None
    mfg_year: int | None = None


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
    shortage_value: Decimal = Decimal("0")  # billed less received, at the bill rate
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
    purchase_order_id: int | None = None
    purchase_order_number: str | None = None
    match_approved: bool = False  # an owner approval let a bill that differs from its order in
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
    weight_variance_pct: Decimal = Decimal("0")
    weight_flagged: bool = False
    shortage_value: Decimal = Decimal("0")
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
    warnings: list[str] = Field(default_factory=list)
