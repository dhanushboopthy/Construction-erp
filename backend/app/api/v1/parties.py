from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentPrincipal, DbSession, OwnerOrCounter
from app.schemas.common import Page
from app.schemas.parties import (
    PartyCreate,
    PartyOut,
    PartyUpdate,
    SiteCreate,
    SiteOut,
    SiteUpdate,
)
from app.services import parties as party_service

router = APIRouter(tags=["parties"])


@router.get("/parties", response_model=Page[PartyOut])
def list_parties(
    _: CurrentPrincipal,
    db: DbSession,
    q: str | None = None,
    kind: Annotated[str | None, Query(pattern="^(customer|supplier)$")] = None,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[PartyOut]:
    rows, total = party_service.list_parties(
        db, q=q, kind=kind, include_inactive=include_inactive, limit=limit, offset=offset
    )
    return Page[PartyOut](
        items=[PartyOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.post("/parties", response_model=PartyOut, status_code=status.HTTP_201_CREATED)
def create_party(body: PartyCreate, principal: OwnerOrCounter, db: DbSession) -> PartyOut:
    return PartyOut.model_validate(
        party_service.create_party(db, body, is_owner=principal.is_owner)
    )


@router.get("/parties/{party_id}", response_model=PartyOut)
def get_party(party_id: int, _: CurrentPrincipal, db: DbSession) -> PartyOut:
    return PartyOut.model_validate(party_service.get_party(db, party_id))


@router.patch("/parties/{party_id}", response_model=PartyOut)
def update_party(
    party_id: int, body: PartyUpdate, principal: OwnerOrCounter, db: DbSession
) -> PartyOut:
    return PartyOut.model_validate(
        party_service.update_party(db, party_id, body, is_owner=principal.is_owner)
    )


@router.post(
    "/parties/{party_id}/sites", response_model=SiteOut, status_code=status.HTTP_201_CREATED
)
def add_site(party_id: int, body: SiteCreate, _: OwnerOrCounter, db: DbSession) -> SiteOut:
    return SiteOut.model_validate(party_service.add_site(db, party_id, body))


@router.patch("/sites/{site_id}", response_model=SiteOut)
def update_site(site_id: int, body: SiteUpdate, _: OwnerOrCounter, db: DbSession) -> SiteOut:
    return SiteOut.model_validate(party_service.update_site(db, site_id, body))
