from fastapi import APIRouter, status

from app.api.deps import CurrentPrincipal, DbSession, OwnerOnly
from app.schemas.location import LocationCreate, LocationOut, LocationUpdate
from app.services import locations as location_service

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("", response_model=list[LocationOut])
def list_locations(
    _: CurrentPrincipal, db: DbSession, include_inactive: bool = False
) -> list[LocationOut]:
    """Every signed-in user can list locations (needed for stock availability and transfers)."""
    rows = location_service.list_locations(db, include_inactive)
    return [LocationOut.model_validate(r) for r in rows]


@router.post("", response_model=LocationOut, status_code=status.HTTP_201_CREATED)
def create_location(body: LocationCreate, _: OwnerOnly, db: DbSession) -> LocationOut:
    return LocationOut.model_validate(location_service.create_location(db, body))


@router.patch("/{location_id}", response_model=LocationOut)
def update_location(
    location_id: int, body: LocationUpdate, _: OwnerOnly, db: DbSession
) -> LocationOut:
    return LocationOut.model_validate(location_service.update_location(db, location_id, body))
