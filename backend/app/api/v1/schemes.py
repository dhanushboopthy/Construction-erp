from fastapi import APIRouter, status

from app.api.deps import DbSession, OwnerOnly, OwnerOrAccountant
from app.schemas.schemes import SchemeCreate, SchemeOut, SchemeUpdate
from app.services import schemes as service

router = APIRouter(prefix="/schemes", tags=["schemes"])


@router.get("", response_model=list[SchemeOut])
def list_schemes(
    _: OwnerOrAccountant, db: DbSession, party_id: int | None = None, alerts_only: bool = False
) -> list[SchemeOut]:
    """Supplier target schemes with progress; `alerts_only` keeps those at 80% or more."""
    return service.list_schemes(db, party_id=party_id, alerts_only=alerts_only)


@router.post("", response_model=SchemeOut, status_code=status.HTTP_201_CREATED)
def create_scheme(body: SchemeCreate, principal: OwnerOnly, db: DbSession) -> SchemeOut:
    return service.view(db, service.create(db, body, actor_id=principal.user_id))


@router.patch("/{scheme_id}", response_model=SchemeOut)
def update_scheme(
    scheme_id: int, body: SchemeUpdate, principal: OwnerOnly, db: DbSession
) -> SchemeOut:
    return service.view(db, service.update(db, scheme_id, body, actor_id=principal.user_id))


@router.post("/{scheme_id}/book-rebate", response_model=SchemeOut)
def book_rebate(scheme_id: int, principal: OwnerOnly, db: DbSession) -> SchemeOut:
    """Record the earned rebate as a credit from the supplier. Once only."""
    return service.view(db, service.book_rebate(db, scheme_id, actor_id=principal.user_id))
