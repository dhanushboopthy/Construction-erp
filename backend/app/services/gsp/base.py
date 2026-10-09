"""The contract every GSP (GST Suvidha Provider) adapter meets. The rest of the app only knows
these types, so the provider can be swapped by configuration (Milestone 10)."""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol


class GspError(Exception):
    """The provider refused or could not be reached. `retryable` means try again later."""

    def __init__(self, message: str, *, code: str = "GSP_ERROR", retryable: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class DocItem:
    hsn: str
    description: str
    quantity: Decimal
    unit: str
    taxable: Decimal
    gst_rate: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal


@dataclass(frozen=True)
class Party:
    name: str
    gstin: str  # "URP" for an unregistered buyer
    address: str
    state_code: str
    pincode: str


@dataclass(frozen=True)
class DocTotals:
    taxable: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    round_off: Decimal
    grand_total: Decimal


@dataclass(frozen=True)
class EwayRequest:
    doc_no: str
    doc_date: date
    supplier: Party
    recipient: Party
    ship_to: Party | None
    totals: DocTotals
    items: list[DocItem]
    distance_km: int
    vehicle_no: str | None  # Part B; may be added later with update_vehicle
    inter_state: bool


@dataclass(frozen=True)
class EwayResult:
    number: str
    generated_at: datetime
    valid_until: date | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IrnRequest:
    doc_no: str
    doc_date: date
    supplier: Party
    buyer: Party
    ship_to: Party | None
    totals: DocTotals
    items: list[DocItem]


@dataclass(frozen=True)
class IrnResult:
    irn: str
    ack_no: str
    ack_date: datetime
    signed_qr: str
    raw: dict[str, Any] = field(default_factory=dict)


class GspClient(Protocol):
    def generate_eway(self, request: EwayRequest) -> EwayResult: ...

    def update_vehicle(
        self, number: str, vehicle_no: str, reason: str, from_place: str
    ) -> dict[str, Any]: ...

    def cancel_eway(self, number: str, reason: str) -> dict[str, Any]: ...

    def generate_irn(self, request: IrnRequest) -> IrnResult: ...

    def cancel_irn(self, irn: str, reason: str) -> dict[str, Any]: ...
