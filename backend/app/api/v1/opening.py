from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DbSession, OwnerOnly
from app.models.enums import OpeningKind, OpeningStatus
from app.schemas.opening import OpeningCreate, OpeningOut, OpeningUpdate, PostRequest, PostResult
from app.services import opening as opening_service

router = APIRouter(prefix="/opening", tags=["opening"])


@router.get("", response_model=list[OpeningOut])
def list_opening(
    _: OwnerOnly,
    db: DbSession,
    kind: Annotated[OpeningKind | None, Query()] = None,
    status_: Annotated[OpeningStatus | None, Query(alias="status")] = None,
) -> list[OpeningOut]:
    return opening_service.list_rows(db, kind=kind, status=status_)


@router.post("", response_model=OpeningOut, status_code=status.HTTP_201_CREATED)
def create_opening(body: OpeningCreate, _: OwnerOnly, db: DbSession) -> OpeningOut:
    row = opening_service.create_row(db, body)
    return opening_service.get_view(db, row.id)


@router.patch("/{row_id}", response_model=OpeningOut)
def update_opening(row_id: int, body: OpeningUpdate, _: OwnerOnly, db: DbSession) -> OpeningOut:
    opening_service.update_row(db, row_id, body)
    return opening_service.get_view(db, row_id)


@router.delete("/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_opening(row_id: int, _: OwnerOnly, db: DbSession) -> None:
    opening_service.delete_row(db, row_id)


@router.post("/post", response_model=PostResult)
def post_opening(body: PostRequest, owner: OwnerOnly, db: DbSession) -> PostResult:
    """Write the drafts of the chosen kinds to the ledgers. This cannot be undone."""
    return opening_service.post(db, body.kinds, owner.user_id)
