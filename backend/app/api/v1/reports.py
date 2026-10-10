from datetime import date

from fastapi import APIRouter

from app.api.deps import CurrentPrincipal, DbSession, OwnerOnly, OwnerOrAccountant
from app.core.clock import today_ist
from app.models.enums import Role
from app.schemas.profitability import Cut, ProfitabilityOut
from app.schemas.reports import ProfitGroup, ProfitReport, SegmentReport, TodayOut
from app.services import profitability as profit_service
from app.services import reports as service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/today", response_model=TodayOut)
def today(principal: CurrentPrincipal, db: DbSession) -> TodayOut:
    """The home-screen figures. Counter staff see their own shop's sales; payables and profit
    are for the owner (payables also for the accountant)."""
    return service.today(
        db,
        location_ids=principal.location_ids if principal.role is Role.COUNTER else None,
        see_payable=principal.role is not Role.COUNTER,
        see_profit=principal.sees_cost,
    )


@router.get("/profit", response_model=ProfitReport)
def profit(
    _: OwnerOnly, db: DbSession, group: ProfitGroup, date_from: date, date_to: date
) -> ProfitReport:
    """Profit by item, customer or site: sales less returns, less cost, less freight."""
    return service.profit_report(db, group, date_from, date_to)


@router.get("/profitability", response_model=ProfitabilityOut)
def profitability(
    _: OwnerOnly,
    db: DbSession,
    by: Cut,
    period: str | None = None,
    location_id: int | None = None,
) -> ProfitabilityOut:
    """Profit for a month by brand, shop, user, item or customer, with profit per ton. The rows
    add up to the profit and loss gross profit once stock lost is taken off (owner only)."""
    return profit_service.profitability(
        db, period or today_ist().strftime("%Y-%m"), by, location_id
    )


@router.get("/sales-by-segment", response_model=SegmentReport)
def sales_by_segment(
    _: OwnerOrAccountant, db: DbSession, start_year: int | None = None
) -> SegmentReport:
    """Monthly sales (excluding GST, less returns) by customer segment for a financial year."""
    return service.sales_by_segment(db, start_year)
