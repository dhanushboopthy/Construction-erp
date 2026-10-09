"""Shops and godowns."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.core.tenancy import TENANT_ID
from app.models.setup import Location
from app.schemas.location import LocationCreate, LocationUpdate


def list_locations(db: Session, include_inactive: bool = False) -> list[Location]:
    stmt = select(Location).where(Location.tenant_id == TENANT_ID).order_by(Location.code)
    if not include_inactive:
        stmt = stmt.where(Location.is_active.is_(True))
    return list(db.execute(stmt).scalars())


def get_location(db: Session, location_id: int) -> Location:
    location = db.get(Location, location_id)
    if location is None or location.tenant_id != TENANT_ID:
        raise NotFoundError("Location not found")
    return location


def create_location(db: Session, data: LocationCreate) -> Location:
    taken = db.execute(
        select(Location.id).where(Location.tenant_id == TENANT_ID, Location.code == data.code)
    ).first()
    if taken:
        raise ConflictError("That code is already used", code="LOCATION_CODE_TAKEN", field="code")
    location = Location(tenant_id=TENANT_ID, **data.model_dump())
    db.add(location)
    db.commit()
    return location


def update_location(db: Session, location_id: int, data: LocationUpdate) -> Location:
    # The code is fixed once created: it is printed inside issued document numbers.
    location = get_location(db, location_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(location, key, value)
    db.commit()
    return location
