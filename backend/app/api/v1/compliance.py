from fastapi import APIRouter, status

from app.api.deps import CurrentPrincipal, DbSession, OwnerOnly, OwnerOrCounter
from app.models.enums import Role
from app.schemas.compliance import (
    EInvoiceCreate,
    EInvoiceOut,
    EInvoiceStatusOut,
    EwayBatchIn,
    EwayBatchOut,
    EwayCancel,
    EwayCreate,
    EwayManual,
    EwayOut,
    EwayStatusOut,
    EwayVehicleUpdate,
    PendingEwayOut,
)
from app.services import compliance as service

router = APIRouter(tags=["compliance"])


@router.get("/invoices/{invoice_id}/eway-bill", response_model=EwayStatusOut)
def eway_status(invoice_id: int, principal: CurrentPrincipal, db: DbSession) -> EwayStatusOut:
    """Is an e-way bill needed for this bill, and the one made for it (if any)."""
    return service.eway_status(db, invoice_id, principal.can_access_location)


@router.post(
    "/invoices/{invoice_id}/eway-bill", response_model=EwayOut, status_code=status.HTTP_201_CREATED
)
def create_eway(
    invoice_id: int, body: EwayCreate, principal: OwnerOrCounter, db: DbSession
) -> EwayOut:
    """Make the e-way bill through the GSP. Nothing is saved if the GSP fails."""
    row = service.generate_eway(
        db, invoice_id, body, actor_id=principal.user_id, can_access=principal.can_access_location
    )
    return service.eway_view(db, row)


@router.post(
    "/invoices/{invoice_id}/eway-bill/manual",
    response_model=EwayOut,
    status_code=status.HTTP_201_CREATED,
)
def record_manual_eway(
    invoice_id: int, body: EwayManual, principal: OwnerOrCounter, db: DbSession
) -> EwayOut:
    """Fallback: record the number of a bill made by hand on the government portal."""
    row = service.record_manual_eway(
        db, invoice_id, body, actor_id=principal.user_id, can_access=principal.can_access_location
    )
    return service.eway_view(db, row)


@router.post("/invoices/{invoice_id}/eway-bill/vehicle", response_model=EwayOut)
def update_eway_vehicle(
    invoice_id: int, body: EwayVehicleUpdate, principal: OwnerOrCounter, db: DbSession
) -> EwayOut:
    row = service.update_eway_vehicle(
        db, invoice_id, body, actor_id=principal.user_id, can_access=principal.can_access_location
    )
    return service.eway_view(db, row)


@router.post("/invoices/{invoice_id}/eway-bill/cancel", response_model=EwayOut)
def cancel_eway(invoice_id: int, body: EwayCancel, principal: OwnerOnly, db: DbSession) -> EwayOut:
    row = service.cancel_eway(
        db, invoice_id, body, actor_id=principal.user_id, can_access=principal.can_access_location
    )
    return service.eway_view(db, row)


@router.get("/eway-bills/pending", response_model=list[PendingEwayOut])
def pending_eway(principal: CurrentPrincipal, db: DbSession) -> list[PendingEwayOut]:
    """Recent delivered bills over the threshold that still have no e-way bill."""
    scope = principal.location_ids if principal.role is Role.COUNTER else None
    return service.pending_eway(db, scope)


@router.post("/eway-bills/batch", response_model=EwayBatchOut)
def batch_eway(body: EwayBatchIn, principal: OwnerOrCounter, db: DbSession) -> EwayBatchOut:
    """Make several e-way bills in one go; each bill succeeds or fails on its own."""
    return service.batch_eway(
        db, body, actor_id=principal.user_id, can_access=principal.can_access_location
    )


@router.get("/invoices/{invoice_id}/einvoice", response_model=EInvoiceStatusOut)
def einvoice_status(
    invoice_id: int, principal: CurrentPrincipal, db: DbSession
) -> EInvoiceStatusOut:
    return service.einvoice_status(db, invoice_id, principal.can_access_location)


@router.post(
    "/invoices/{invoice_id}/einvoice",
    response_model=EInvoiceOut,
    status_code=status.HTTP_201_CREATED,
)
def create_einvoice(
    invoice_id: int, body: EInvoiceCreate, principal: OwnerOrCounter, db: DbSession
) -> EInvoiceOut:
    row = service.generate_einvoice(
        db, invoice_id, body, actor_id=principal.user_id, can_access=principal.can_access_location
    )
    return service.einvoice_view(row)


@router.post("/invoices/{invoice_id}/einvoice/cancel", response_model=EInvoiceOut)
def cancel_einvoice(
    invoice_id: int, body: EwayCancel, principal: OwnerOnly, db: DbSession
) -> EInvoiceOut:
    row = service.cancel_einvoice(
        db, invoice_id, body, actor_id=principal.user_id, can_access=principal.can_access_location
    )
    return service.einvoice_view(row)
