from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from app.models.enums import ComplianceStatus, EwaySource
from app.schemas.common import Schema


class EwayCreate(Schema):
    distance_km: int = Field(ge=1, le=4000)
    from_pincode: str = Field(pattern=r"^[1-9][0-9]{5}$")
    to_pincode: str = Field(pattern=r"^[1-9][0-9]{5}$")
    vehicle_no: str | None = Field(default=None, max_length=20)  # Part B; can be added later


class EwayVehicleUpdate(Schema):
    vehicle_no: str = Field(min_length=4, max_length=20)
    reason: str = Field(min_length=3, max_length=100)  # breakdown, transhipment, first time...
    from_place: str = Field(min_length=2, max_length=100)


class EwayCancel(Schema):
    reason: str = Field(min_length=3, max_length=200)


class EwayManual(Schema):
    """A bill made on the government portal by hand: the number is typed in (fallback)."""

    number: str = Field(pattern=r"^[0-9]{12}$")
    vehicle_no: str | None = Field(default=None, max_length=20)
    valid_until: date | None = None


class EwayOut(Schema):
    id: int
    invoice_id: int
    invoice_number: str
    number: str
    status: ComplianceStatus
    source: EwaySource
    vehicle_no: str | None
    distance_km: int | None
    valid_until: date | None
    generated_at: datetime
    cancelled_at: datetime | None
    cancel_reason: str | None
    can_cancel: bool


class EwayStatusOut(Schema):
    invoice_id: int
    required: bool
    threshold: Decimal
    live: EwayOut | None
    history: list[EwayOut]


class EwayBatchItem(EwayCreate):
    invoice_id: int


class EwayBatchIn(Schema):
    items: list[EwayBatchItem] = Field(min_length=1, max_length=100)


class EwayBatchRow(Schema):
    invoice_id: int
    ok: bool
    number: str | None = None
    code: str | None = None
    message: str | None = None


class EwayBatchOut(Schema):
    results: list[EwayBatchRow]
    succeeded: int
    failed: int


class PendingEwayOut(Schema):
    invoice_id: int
    number: str
    invoice_date: date
    party_name: str
    grand_total: Decimal
    inter_state: bool


class EInvoiceCreate(Schema):
    from_pincode: str = Field(pattern=r"^[1-9][0-9]{5}$")
    to_pincode: str = Field(pattern=r"^[1-9][0-9]{5}$")


class EInvoiceOut(Schema):
    id: int
    invoice_id: int
    irn: str
    ack_no: str
    ack_date: datetime
    status: ComplianceStatus
    cancelled_at: datetime | None
    cancel_reason: str | None
    can_cancel: bool


class EInvoiceStatusOut(Schema):
    invoice_id: int
    enabled: bool
    required: bool
    einvoice: EInvoiceOut | None
