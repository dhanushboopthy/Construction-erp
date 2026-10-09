from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DbSession, OwnerOnly, OwnerOrAccountant, OwnerOrCounter
from app.schemas.common import Page
from app.schemas.transport import (
    DropShipReport,
    LinkCreate,
    LinkOut,
    OpenDirectLineOut,
    TripCreate,
    TripOut,
    VehicleCreate,
    VehicleOut,
    VehicleUpdate,
)
from app.services import transport as service

router = APIRouter(tags=["transport"])


@router.get("/vehicles", response_model=list[VehicleOut])
def list_vehicles(
    _: OwnerOrAccountant, db: DbSession, include_inactive: bool = False
) -> list[VehicleOut]:
    return [VehicleOut.model_validate(v) for v in service.list_vehicles(db, include_inactive)]


@router.post("/vehicles", response_model=VehicleOut, status_code=status.HTTP_201_CREATED)
def create_vehicle(body: VehicleCreate, principal: OwnerOnly, db: DbSession) -> VehicleOut:
    return VehicleOut.model_validate(service.create_vehicle(db, body, actor_id=principal.user_id))


@router.patch("/vehicles/{vehicle_id}", response_model=VehicleOut)
def update_vehicle(
    vehicle_id: int, body: VehicleUpdate, principal: OwnerOnly, db: DbSession
) -> VehicleOut:
    return VehicleOut.model_validate(
        service.update_vehicle(db, vehicle_id, body, actor_id=principal.user_id)
    )


@router.get("/trips", response_model=Page[TripOut])
def list_trips(
    _: OwnerOrAccountant,
    db: DbSession,
    invoice_id: int | None = None,
    vehicle_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[TripOut]:
    rows, total = service.list_trips(
        db, invoice_id=invoice_id, vehicle_id=vehicle_id, limit=limit, offset=offset
    )
    return Page[TripOut](
        items=[service.trip_view(db, r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.post("/trips", response_model=TripOut, status_code=status.HTTP_201_CREATED)
def create_trip(body: TripCreate, principal: OwnerOnly, db: DbSession) -> TripOut:
    """Record a run. Freight becomes payable to the vehicle's owner (pay it in /payments)."""
    return service.trip_view(db, service.create_trip(db, body, actor_id=principal.user_id))


@router.get("/drop-ship/open-purchases", response_model=list[OpenDirectLineOut])
def open_direct_lines(
    _: OwnerOrCounter, db: DbSession, item_id: int | None = None
) -> list[OpenDirectLineOut]:
    """Direct supplier purchases not yet claimed by a sale. Quantities only, never cost."""
    return service.open_direct_lines(db, item_id)


@router.post("/drop-ship/links", response_model=LinkOut, status_code=status.HTTP_201_CREATED)
def link_sale_to_purchase(body: LinkCreate, principal: OwnerOnly, db: DbSession) -> LinkOut:
    return LinkOut.model_validate(service.link_after_billing(db, body, actor_id=principal.user_id))


@router.get("/reports/drop-ship", response_model=DropShipReport)
def drop_ship_report(_: OwnerOnly, db: DbSession) -> DropShipReport:
    """Direct sales with purchase cost, freight and profit; unlinked sales are flagged."""
    return service.report(db)
