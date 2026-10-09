from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import Field, field_validator

from app.schemas.common import Schema

Amount = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]


class VehicleCreate(Schema):
    number: str = Field(min_length=4, max_length=20)
    owner_name: str = Field(min_length=2, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    is_own: bool = False

    @field_validator("number")
    @classmethod
    def _plate(cls, value: str) -> str:
        return "".join(value.upper().split())


class VehicleUpdate(Schema):
    owner_name: str | None = Field(default=None, min_length=2, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    is_active: bool | None = None


class VehicleOut(Schema):
    id: int
    number: str
    owner_name: str
    phone: str | None
    is_own: bool
    party_id: int | None
    is_active: bool


class TripCreate(Schema):
    vehicle_id: int
    location_id: int
    trip_date: date | None = None
    invoice_id: int | None = None
    purchase_id: int | None = None
    from_place: str = Field(min_length=2, max_length=150)
    to_place: str = Field(min_length=2, max_length=150)
    freight_amount: Amount
    note: str | None = Field(default=None, max_length=300)


class TripOut(Schema):
    id: int
    trip_date: date
    vehicle_id: int
    vehicle_number: str
    owner_name: str
    location_id: int
    invoice_id: int | None
    invoice_number: str | None
    purchase_id: int | None
    purchase_number: str | None
    from_place: str
    to_place: str
    freight_amount: Decimal
    paid_amount: Decimal
    pay_ref: str | None  # the bill number to aim a payment at in /payments
    note: str | None


class OpenDirectLineOut(Schema):
    """A direct supplier purchase line that no sale has fully claimed. No cost is shown."""

    purchase_line_id: int
    purchase_number: str
    supplier_name: str
    bill_no: str
    bill_date: date
    item_id: int
    item_name: str
    free_qty: Decimal
    base_unit: str


class LinkCreate(Schema):
    sales_line_id: int
    purchase_line_id: int


class LinkOut(Schema):
    id: int
    sales_line_id: int
    purchase_line_id: int
    base_qty: Decimal
    unit_cost: Decimal


class DropShipRow(Schema):
    invoice_id: int
    invoice_number: str
    invoice_date: date
    customer: str
    sales_line_id: int
    item_name: str
    base_qty: Decimal
    base_unit: str
    taxable: Decimal
    purchase_number: str | None
    supplier_name: str | None
    goods_cost: Decimal | None  # null until the sale is linked to its purchase
    freight: Decimal
    profit: Decimal | None


class DropShipReport(Schema):
    rows: list[DropShipRow]
    unlinked: int
    profit_total: Decimal
