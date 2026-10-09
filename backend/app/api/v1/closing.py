from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentPrincipal, DbSession, OwnerOnly, OwnerOrCounter
from app.models.enums import Role
from app.schemas.closing import ClosingCreate, ClosingOut, ClosingPreview, ReopenIn
from app.schemas.common import Page
from app.services import closing as service
from app.services import reports

router = APIRouter(prefix="/closings", tags=["closing"])


@router.get("/preview", response_model=ClosingPreview)
def preview(
    principal: CurrentPrincipal, db: DbSession, location_id: int, closing_date: date
) -> ClosingPreview:
    """The day's figures and the cash that should be in the drawer. Profit for the owner only."""
    return service.preview(
        db,
        location_id,
        closing_date,
        can_access=principal.can_access_location,
        profit=(lambda loc, on: reports.profit_for_day(db, loc, on))
        if principal.sees_cost
        else None,
    )


@router.post("", response_model=ClosingOut, status_code=status.HTTP_201_CREATED)
def close_day(body: ClosingCreate, principal: OwnerOrCounter, db: DbSession) -> ClosingOut:
    """Count the drawer and close the shop-day. Later documents for that day are refused."""
    row = service.close_day(
        db, body, actor_id=principal.user_id, can_access=principal.can_access_location
    )
    return service.view(db, row)


@router.post("/{closing_id}/reopen", response_model=ClosingOut)
def reopen(closing_id: int, body: ReopenIn, principal: OwnerOnly, db: DbSession) -> ClosingOut:
    row = service.reopen_day(db, closing_id, body, actor_id=principal.user_id)
    return service.view(db, row)


@router.get("", response_model=Page[ClosingOut])
def list_closings(
    principal: CurrentPrincipal,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ClosingOut]:
    scope = principal.location_ids if principal.role is Role.COUNTER else None
    rows, total = service.list_closings(db, location_ids=scope, limit=limit, offset=offset)
    return Page[ClosingOut](
        items=[service.view(db, r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/{closing_id}/pdf", response_class=Response)
def closing_pdf(closing_id: int, principal: CurrentPrincipal, db: DbSession) -> Response:
    row, data = service.get_pdf(db, closing_id, can_access=principal.can_access_location)
    return Response(
        data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="closing-{row.closing_date.isoformat()}.pdf"'
        },
    )
