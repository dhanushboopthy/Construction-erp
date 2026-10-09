from fastapi import APIRouter, status

from app.api.deps import CurrentPrincipal, DbSession, OwnerOnly, OwnerOrCounter
from app.core.errors import NotFoundError
from app.models.enums import Role
from app.schemas.stock_ops import (
    CountCreate,
    CountLinesUpdate,
    CountOut,
    CountOwnerOut,
    TransferCreate,
    TransferOut,
)
from app.services import stock_ops

router = APIRouter(tags=["stock"])


def _scope(principal: CurrentPrincipal) -> frozenset[int] | None:
    return principal.location_ids if principal.role is Role.COUNTER else None


@router.post("/transfers", response_model=TransferOut, status_code=status.HTTP_201_CREATED)
def create_transfer(body: TransferCreate, principal: OwnerOrCounter, db: DbSession) -> TransferOut:
    return stock_ops.create_transfer(
        db,
        body,
        actor_id=principal.user_id,
        can_access_from=principal.can_access_location(body.from_location_id),
    )


@router.get("/transfers", response_model=list[TransferOut])
def list_transfers(principal: CurrentPrincipal, db: DbSession) -> list[TransferOut]:
    return stock_ops.list_transfers(db, _scope(principal))


@router.get("/transfers/{transfer_id}", response_model=TransferOut)
def get_transfer(transfer_id: int, principal: CurrentPrincipal, db: DbSession) -> TransferOut:
    transfer = stock_ops.get_transfer(db, transfer_id)
    scope = _scope(principal)
    if scope is not None and not ({transfer.from_location_id, transfer.to_location_id} & scope):
        raise NotFoundError("Transfer not found")
    return transfer


@router.post(
    "/stock-counts", response_model=CountOwnerOut | CountOut, status_code=status.HTTP_201_CREATED
)
def open_count(
    body: CountCreate, principal: OwnerOrCounter, db: DbSession
) -> CountOwnerOut | CountOut:
    row = stock_ops.open_count(
        db,
        body,
        actor_id=principal.user_id,
        can_access=principal.can_access_location(body.location_id),
    )
    return stock_ops.count_view(db, row, principal.sees_cost)


@router.get("/stock-counts", response_model=list[CountOwnerOut] | list[CountOut])
def list_counts(principal: CurrentPrincipal, db: DbSession) -> list[CountOwnerOut] | list[CountOut]:
    rows = stock_ops.list_counts(db, _scope(principal))
    return [stock_ops.count_view(db, r, principal.sees_cost) for r in rows]


@router.get("/stock-counts/{count_id}", response_model=CountOwnerOut | CountOut)
def get_count(
    count_id: int, principal: CurrentPrincipal, db: DbSession
) -> CountOwnerOut | CountOut:
    row = stock_ops.get_count(db, count_id)
    if not principal.can_access_location(row.location_id):
        raise NotFoundError("Count not found")
    return stock_ops.count_view(db, row, principal.sees_cost)


@router.put("/stock-counts/{count_id}/lines", response_model=CountOwnerOut | CountOut)
def enter_counts(
    count_id: int, body: CountLinesUpdate, principal: OwnerOrCounter, db: DbSession
) -> CountOwnerOut | CountOut:
    row = stock_ops.get_count(db, count_id)
    if not principal.can_access_location(row.location_id):
        raise NotFoundError("Count not found")
    row = stock_ops.enter_counts(db, count_id, body)
    return stock_ops.count_view(db, row, principal.sees_cost)


@router.post("/stock-counts/{count_id}/post", response_model=CountOwnerOut)
def post_count(count_id: int, owner: OwnerOnly, db: DbSession) -> CountOwnerOut:
    """Only the owner turns a count into stock adjustments."""
    row = stock_ops.post_count(db, count_id, owner.user_id)
    view = stock_ops.count_view(db, row, True)
    assert isinstance(view, CountOwnerOut)  # noqa: S101
    return view
