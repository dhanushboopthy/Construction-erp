"""E-way bills and e-invoices (IRN) for issued sales invoices (Milestone 10).

The provider is called through `services.gsp` (fake in dev, sandbox or live by configuration).
Nothing is saved when the provider fails, so a retry is always safe; one live e-way bill per
invoice is guaranteed by a partial unique index and an advisory lock around the call."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import today_ist
from app.core.errors import (
    AppError,
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    UpstreamError,
)
from app.core.tenancy import TENANT_ID
from app.domain import eway as eway_rules
from app.domain.compliance import eway_bill_required
from app.domain.gst import SupplyKind
from app.models.compliance import EInvoice, EwayBill
from app.models.enums import ComplianceStatus, EwaySource
from app.models.sales import SalesInvoice
from app.models.setup import ShopSettings
from app.schemas.compliance import (
    EInvoiceCreate,
    EInvoiceOut,
    EInvoiceStatusOut,
    EwayBatchIn,
    EwayBatchOut,
    EwayBatchRow,
    EwayCancel,
    EwayCreate,
    EwayManual,
    EwayOut,
    EwayStatusOut,
    EwayVehicleUpdate,
    PendingEwayOut,
)
from app.services import gsp
from app.services.gsp.base import (
    DocItem,
    DocTotals,
    EwayRequest,
    GspClient,
    GspError,
    IrnRequest,
    Party,
)
from app.services.shop_settings import get_settings_row

# Look-back for invoices still waiting for an e-way bill.
PENDING_DAYS = 30


def _now() -> datetime:
    return datetime.now(UTC)


def _client() -> GspClient:
    try:
        return gsp.get_client()
    except GspError as exc:
        raise UpstreamError(exc.message, code=exc.code) from exc


def _call[T](action: Callable[[], T]) -> T:
    """Run a provider call; turn its failure into a 502 that saves nothing."""
    try:
        return action()
    except GspError as exc:
        raise UpstreamError(
            exc.message + (" Try again in a minute." if exc.retryable else ""), code=exc.code
        ) from exc


def _invoice(db: Session, invoice_id: int, can_access: Callable[[int], bool]) -> SalesInvoice:
    inv = db.get(SalesInvoice, invoice_id)
    if inv is None or inv.tenant_id != TENANT_ID or not can_access(inv.location_id):
        raise NotFoundError("Invoice not found", field="invoice_id")
    return inv


def _log(row: EwayBill | EInvoice, call: str, response: dict[str, Any]) -> None:
    row.responses = [*row.responses, {"call": call, "at": _now().isoformat(), "response": response}]


# ---------------------------------------------------------------------------- views


def eway_view(db: Session, row: EwayBill) -> EwayOut:
    inv = db.get(SalesInvoice, row.invoice_id)
    cancellable = row.status is ComplianceStatus.GENERATED and eway_rules.can_cancel(
        row.generated_at, _now()
    )
    return EwayOut(
        id=row.id,
        invoice_id=row.invoice_id,
        invoice_number=inv.number if inv else "",
        number=row.number,
        status=row.status,
        source=row.source,
        vehicle_no=row.vehicle_no,
        distance_km=row.distance_km,
        valid_until=row.valid_until,
        generated_at=row.generated_at,
        cancelled_at=row.cancelled_at,
        cancel_reason=row.cancel_reason,
        can_cancel=cancellable,
    )


def einvoice_view(row: EInvoice) -> EInvoiceOut:
    return EInvoiceOut(
        id=row.id,
        invoice_id=row.invoice_id,
        irn=row.irn,
        ack_no=row.ack_no,
        ack_date=row.ack_date,
        status=row.status,
        cancelled_at=row.cancelled_at,
        cancel_reason=row.cancel_reason,
        can_cancel=row.status is ComplianceStatus.GENERATED
        and eway_rules.can_cancel(row.ack_date, _now()),
    )


def _bills(db: Session, invoice_id: int) -> list[EwayBill]:
    return list(
        db.execute(
            select(EwayBill)
            .where(EwayBill.tenant_id == TENANT_ID, EwayBill.invoice_id == invoice_id)
            .order_by(EwayBill.id.desc())
        ).scalars()
    )


def live_eway(db: Session, invoice_id: int) -> EwayBill | None:
    return next((b for b in _bills(db, invoice_id) if b.status is ComplianceStatus.GENERATED), None)


def live_einvoice(db: Session, invoice_id: int) -> EInvoice | None:
    row = db.execute(
        select(EInvoice).where(EInvoice.tenant_id == TENANT_ID, EInvoice.invoice_id == invoice_id)
    ).scalar_one_or_none()
    return row if row and row.status is ComplianceStatus.GENERATED else None


def _required(settings: ShopSettings, inv: SalesInvoice) -> bool:
    return eway_bill_required(
        inv.grand_total,
        inv.supply_kind is SupplyKind.INTER_STATE,
        settings.eway_threshold_interstate,
        settings.eway_threshold_intrastate,
    )


def eway_status(db: Session, invoice_id: int, can_access: Callable[[int], bool]) -> EwayStatusOut:
    inv = _invoice(db, invoice_id, can_access)
    settings = get_settings_row(db)
    bills = _bills(db, inv.id)
    live = next((b for b in bills if b.status is ComplianceStatus.GENERATED), None)
    return EwayStatusOut(
        invoice_id=inv.id,
        required=_required(settings, inv),
        threshold=settings.eway_threshold_interstate
        if inv.supply_kind is SupplyKind.INTER_STATE
        else settings.eway_threshold_intrastate,
        live=eway_view(db, live) if live else None,
        history=[eway_view(db, b) for b in bills],
    )


def einvoice_status(
    db: Session, invoice_id: int, can_access: Callable[[int], bool]
) -> EInvoiceStatusOut:
    inv = _invoice(db, invoice_id, can_access)
    settings = get_settings_row(db)
    row = db.execute(
        select(EInvoice).where(EInvoice.tenant_id == TENANT_ID, EInvoice.invoice_id == inv.id)
    ).scalar_one_or_none()
    return EInvoiceStatusOut(
        invoice_id=inv.id,
        enabled=settings.einvoice_enabled,
        required=eway_rules.einvoice_required(settings.einvoice_enabled, inv.bill_to_gstin),
        einvoice=einvoice_view(row) if row else None,
    )


# ---------------------------------------------------------------------------- requests


def _seller(settings: ShopSettings, pincode: str) -> Party:
    if not settings.gstin:
        raise BusinessRuleError(
            "Enter the shop's GSTIN in Settings before making e-way bills or e-invoices",
            code="SELLER_GSTIN_MISSING",
        )
    return Party(
        name=settings.legal_name,
        gstin=settings.gstin,
        address=settings.address,
        state_code=settings.state_code,
        pincode=pincode,
    )


def _recipient(inv: SalesInvoice, pincode: str) -> Party:
    return Party(
        name=inv.bill_to_name,
        gstin=eway_rules.recipient_gstin(inv.bill_to_gstin),
        address=inv.bill_to_address,
        state_code=inv.place_of_supply,
        pincode=pincode,
    )


def _ship_to(inv: SalesInvoice, pincode: str) -> Party | None:
    if not inv.ship_to_name:
        return None
    return Party(
        name=inv.ship_to_name,
        gstin=eway_rules.recipient_gstin(inv.ship_to_gstin),
        address=inv.ship_to_address or "",
        state_code=inv.place_of_supply,
        pincode=pincode,
    )


def _items(inv: SalesInvoice) -> list[DocItem]:
    return [
        DocItem(
            hsn=x.hsn,
            description=x.description,
            quantity=x.base_qty,
            unit=x.base_unit,
            taxable=x.taxable,
            gst_rate=x.gst_rate,
            cgst=x.cgst,
            sgst=x.sgst,
            igst=x.igst,
        )
        for x in inv.lines
    ]


def _totals(inv: SalesInvoice) -> DocTotals:
    return DocTotals(
        taxable=inv.taxable_value,
        cgst=inv.cgst,
        sgst=inv.sgst,
        igst=inv.igst,
        round_off=inv.round_off,
        grand_total=inv.grand_total,
    )


def _require_vehicle(raw: str) -> str:
    try:
        return eway_rules.normalize_vehicle(raw)
    except ValueError as exc:
        raise BusinessRuleError(
            str(exc).capitalize(), code="VEHICLE_INVALID", field="vehicle_no"
        ) from exc


def _vehicle(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        return eway_rules.normalize_vehicle(raw)
    except ValueError as exc:
        raise BusinessRuleError(
            str(exc).capitalize(), code="VEHICLE_INVALID", field="vehicle_no"
        ) from exc


# ---------------------------------------------------------------------------- e-way bill


def generate_eway(
    db: Session,
    invoice_id: int,
    data: EwayCreate,
    *,
    actor_id: int,
    can_access: Callable[[int], bool],
) -> EwayBill:
    inv = _invoice(db, invoice_id, can_access)
    db.execute(select(func.pg_advisory_xact_lock(3, inv.id)))
    if live_eway(db, inv.id):
        raise ConflictError("This bill already has an e-way bill", code="EWAY_EXISTS")
    settings = get_settings_row(db)
    vehicle = _vehicle(data.vehicle_no)
    request = EwayRequest(
        doc_no=inv.number,
        doc_date=inv.invoice_date,
        supplier=_seller(settings, data.from_pincode),
        recipient=_recipient(inv, data.to_pincode),
        ship_to=_ship_to(inv, data.to_pincode),
        totals=_totals(inv),
        items=_items(inv),
        distance_km=data.distance_km,
        vehicle_no=vehicle,
        inter_state=inv.supply_kind is SupplyKind.INTER_STATE,
    )
    client = _client()
    result = _call(lambda: client.generate_eway(request))
    row = EwayBill(
        tenant_id=TENANT_ID,
        invoice_id=inv.id,
        number=result.number,
        status=ComplianceStatus.GENERATED,
        source=EwaySource.GSP,
        vehicle_no=vehicle,
        from_pincode=data.from_pincode,
        to_pincode=data.to_pincode,
        distance_km=data.distance_km,
        generated_at=result.generated_at,
        valid_until=result.valid_until or eway_rules.valid_until(today_ist(), data.distance_km),
        responses=[],
        created_by=actor_id,
    )
    _log(row, "generate", result.raw)
    db.add(row)
    db.commit()
    return row


def record_manual_eway(
    db: Session,
    invoice_id: int,
    data: EwayManual,
    *,
    actor_id: int,
    can_access: Callable[[int], bool],
) -> EwayBill:
    inv = _invoice(db, invoice_id, can_access)
    db.execute(select(func.pg_advisory_xact_lock(3, inv.id)))
    if live_eway(db, inv.id):
        raise ConflictError("This bill already has an e-way bill", code="EWAY_EXISTS")
    taken = db.execute(
        select(EwayBill.id).where(EwayBill.tenant_id == TENANT_ID, EwayBill.number == data.number)
    ).first()
    if taken:
        raise ConflictError("This e-way bill number is already recorded", code="EWAY_NUMBER_USED")
    row = EwayBill(
        tenant_id=TENANT_ID,
        invoice_id=inv.id,
        number=data.number,
        status=ComplianceStatus.GENERATED,
        source=EwaySource.MANUAL,
        vehicle_no=_vehicle(data.vehicle_no),
        generated_at=_now(),
        valid_until=data.valid_until,
        responses=[],
        created_by=actor_id,
    )
    _log(row, "manual", {"note": "typed in from the portal"})
    db.add(row)
    db.commit()
    return row


def update_eway_vehicle(
    db: Session,
    invoice_id: int,
    data: EwayVehicleUpdate,
    *,
    actor_id: int,
    can_access: Callable[[int], bool],
) -> EwayBill:
    inv = _invoice(db, invoice_id, can_access)
    row = live_eway(db, inv.id)
    if row is None:
        raise NotFoundError("This bill has no live e-way bill")
    vehicle = _require_vehicle(data.vehicle_no)
    client = _client()
    answer = _call(lambda: client.update_vehicle(row.number, vehicle, data.reason, data.from_place))
    row.vehicle_no = vehicle
    row.updated_by = actor_id
    _log(row, "vehicle", answer)
    db.commit()
    return row


def cancel_eway(
    db: Session,
    invoice_id: int,
    data: EwayCancel,
    *,
    actor_id: int,
    can_access: Callable[[int], bool],
) -> EwayBill:
    inv = _invoice(db, invoice_id, can_access)
    db.execute(select(func.pg_advisory_xact_lock(3, inv.id)))
    row = live_eway(db, inv.id)
    if row is None:
        raise NotFoundError("This bill has no live e-way bill")
    if not eway_rules.can_cancel(row.generated_at, _now()):
        raise BusinessRuleError(
            "An e-way bill can only be cancelled within 24 hours of making it",
            code="EWAY_CANCEL_WINDOW_CLOSED",
        )
    if row.source is EwaySource.GSP:
        client = _client()
        answer = _call(lambda: client.cancel_eway(row.number, data.reason))
    else:
        answer = {"note": "made on the portal by hand; cancel it there too"}
    row.status = ComplianceStatus.CANCELLED
    row.cancelled_at = _now()
    row.cancel_reason = data.reason
    row.updated_by = actor_id
    _log(row, "cancel", answer)
    db.commit()
    return row


def pending_eway(db: Session, location_ids: frozenset[int] | None) -> list[PendingEwayOut]:
    """Recent invoices over the threshold with no live e-way bill."""
    settings = get_settings_row(db)
    since = today_ist() - timedelta(days=PENDING_DAYS)
    stmt = select(SalesInvoice).where(
        SalesInvoice.tenant_id == TENANT_ID, SalesInvoice.invoice_date >= since
    )
    if location_ids is not None:
        stmt = stmt.where(SalesInvoice.location_id.in_(location_ids))
    live = set(
        db.execute(
            select(EwayBill.invoice_id).where(
                EwayBill.tenant_id == TENANT_ID, EwayBill.status == ComplianceStatus.GENERATED
            )
        ).scalars()
    )
    out = [
        PendingEwayOut(
            invoice_id=inv.id,
            number=inv.number,
            invoice_date=inv.invoice_date,
            party_name=inv.bill_to_name,
            grand_total=inv.grand_total,
            inter_state=inv.supply_kind is SupplyKind.INTER_STATE,
        )
        for inv in db.execute(
            stmt.order_by(SalesInvoice.invoice_date.desc(), SalesInvoice.id)
        ).scalars()
        if inv.id not in live
        and inv.ship_to_name is not None  # delivered goods; a counter pickup has no transport
        and _required(settings, inv)
    ]
    return out


def batch_eway(
    db: Session, data: EwayBatchIn, *, actor_id: int, can_access: Callable[[int], bool]
) -> EwayBatchOut:
    rows: list[EwayBatchRow] = []
    for item in data.items:
        body = EwayCreate(
            distance_km=item.distance_km,
            from_pincode=item.from_pincode,
            to_pincode=item.to_pincode,
            vehicle_no=item.vehicle_no,
        )
        try:
            made = generate_eway(
                db, item.invoice_id, body, actor_id=actor_id, can_access=can_access
            )
            rows.append(EwayBatchRow(invoice_id=item.invoice_id, ok=True, number=made.number))
        except AppError as exc:
            db.rollback()
            rows.append(
                EwayBatchRow(
                    invoice_id=item.invoice_id, ok=False, code=exc.code, message=exc.message
                )
            )
    ok = sum(1 for r in rows if r.ok)
    return EwayBatchOut(results=rows, succeeded=ok, failed=len(rows) - ok)


# ---------------------------------------------------------------------------- e-invoice


def generate_einvoice(
    db: Session,
    invoice_id: int,
    data: EInvoiceCreate,
    *,
    actor_id: int,
    can_access: Callable[[int], bool],
) -> EInvoice:
    inv = _invoice(db, invoice_id, can_access)
    db.execute(select(func.pg_advisory_xact_lock(4, inv.id)))
    settings = get_settings_row(db)
    if not eway_rules.einvoice_required(settings.einvoice_enabled, inv.bill_to_gstin):
        raise BusinessRuleError(
            "E-invoicing is off, or this is a bill without a buyer GSTIN",
            code="EINVOICE_NOT_REQUIRED",
        )
    existing = db.execute(
        select(EInvoice).where(EInvoice.tenant_id == TENANT_ID, EInvoice.invoice_id == inv.id)
    ).scalar_one_or_none()
    if existing:
        raise ConflictError("This bill already has an IRN", code="EINVOICE_EXISTS")
    request = IrnRequest(
        doc_no=inv.number,
        doc_date=inv.invoice_date,
        supplier=_seller(settings, data.from_pincode),
        buyer=_recipient(inv, data.to_pincode),
        ship_to=_ship_to(inv, data.to_pincode),
        totals=_totals(inv),
        items=_items(inv),
    )
    client = _client()
    result = _call(lambda: client.generate_irn(request))
    row = EInvoice(
        tenant_id=TENANT_ID,
        invoice_id=inv.id,
        irn=result.irn,
        ack_no=result.ack_no,
        ack_date=result.ack_date,
        signed_qr=result.signed_qr,
        status=ComplianceStatus.GENERATED,
        responses=[],
        created_by=actor_id,
    )
    _log(row, "generate", result.raw)
    db.add(row)
    db.commit()
    return row


def cancel_einvoice(
    db: Session,
    invoice_id: int,
    data: EwayCancel,
    *,
    actor_id: int,
    can_access: Callable[[int], bool],
) -> EInvoice:
    inv = _invoice(db, invoice_id, can_access)
    db.execute(select(func.pg_advisory_xact_lock(4, inv.id)))
    row = live_einvoice(db, inv.id)
    if row is None:
        raise NotFoundError("This bill has no live IRN")
    if not eway_rules.can_cancel(row.ack_date, _now()):
        raise BusinessRuleError(
            "An IRN can only be cancelled within 24 hours of making it",
            code="EINVOICE_CANCEL_WINDOW_CLOSED",
        )
    client = _client()
    answer = _call(lambda: client.cancel_irn(row.irn, data.reason))
    row.status = ComplianceStatus.CANCELLED
    row.cancelled_at = _now()
    row.cancel_reason = data.reason
    row.updated_by = actor_id
    _log(row, "cancel", answer)
    db.commit()
    return row
