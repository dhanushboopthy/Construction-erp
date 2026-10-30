from fastapi import APIRouter

from app.api.deps import CurrentPrincipal, DbSession
from app.core.clock import today_ist
from app.schemas.inventory import StockDashboardOut, StockDashboardOwnerOut
from app.schemas.stock import StockItemOut, StockItemOwnerOut
from app.services import inventory, ledgers

router = APIRouter(prefix="/stock", tags=["stock"])


@router.get("/dashboard", response_model=StockDashboardOwnerOut | StockDashboardOut)
def stock_dashboard(
    principal: CurrentPrincipal, db: DbSession
) -> StockDashboardOwnerOut | StockDashboardOut:
    """Stock on one screen: in stock by place and category, run out, to reorder. Values: owner."""
    return inventory.stock_dashboard(db, today_ist(), principal.sees_cost)


@router.get("", response_model=list[StockItemOwnerOut] | list[StockItemOut])
def stock_summary(
    principal: CurrentPrincipal,
    db: DbSession,
    location_id: int | None = None,
    q: str | None = None,
    include_zero: bool = False,
) -> list[StockItemOwnerOut] | list[StockItemOut]:
    """Stock per item and location, rebuilt from the ledger. Cost and value: owner only."""
    return ledgers.stock_summary(
        db,
        with_cost=principal.sees_cost,
        location_id=location_id,
        q=q,
        include_zero=include_zero,
    )
