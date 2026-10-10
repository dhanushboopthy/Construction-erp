"""The lost-sales log and fill rate (FM10)."""

from datetime import date, timedelta

from fastapi import APIRouter, status

from app.api.deps import DbSession, OwnerOrCounter
from app.core.clock import today_ist
from app.models.enums import Role
from app.schemas.orders import FillRateReport, LostSaleCreate, LostSaleOut, LostSaleOwnerOut
from app.services import lost_sales as service

router = APIRouter(tags=["demand"])


def _scope(principal: OwnerOrCounter) -> frozenset[int] | None:
    return principal.location_ids if principal.role is Role.COUNTER else None


@router.post(
    "/lost-sales",
    response_model=LostSaleOwnerOut | LostSaleOut,
    status_code=status.HTTP_201_CREATED,
)
def log_lost_sale(
    body: LostSaleCreate, principal: OwnerOrCounter, db: DbSession
) -> LostSaleOut | LostSaleOwnerOut:
    """Log "asked for, out of stock": item, quantity, an optional note. Counter staff log for their
    own shop, dated today, and see quantities only; the owner also sees the value."""
    row = service.create(
        db,
        body,
        actor_id=principal.user_id,
        is_owner=principal.is_owner,
        can_access=principal.can_access_location(body.location_id),
    )
    return service.view_one(db, row, owner=principal.sees_cost)


@router.get("/lost-sales", response_model=list[LostSaleOwnerOut | LostSaleOut])
def list_lost_sales(
    principal: OwnerOrCounter,
    db: DbSession,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[LostSaleOut | LostSaleOwnerOut]:
    end = date_to or today_ist()
    return service.list_entries(
        db,
        date_from or end - timedelta(days=7),
        end,
        _scope(principal),
        owner=principal.sees_cost,
    )


@router.get("/reports/fill-rate", response_model=FillRateReport)
def fill_rate(
    principal: OwnerOrCounter, db: DbSession, period: str | None = None
) -> FillRateReport:
    """Quantity supplied ÷ quantity asked for (bills plus the lost-sales log), per item. Counter
    staff see their own shop, quantities only; the owner also sees the value lost."""
    return service.fill_rate(
        db,
        period or today_ist().strftime("%Y-%m"),
        _scope(principal),
        owner=principal.sees_cost,
    )
