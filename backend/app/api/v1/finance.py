"""Cash book, expense heads, profit and loss, and KPI definitions (FM1)."""

from datetime import date

from fastapi import APIRouter, status

from app.api.deps import CurrentPrincipal, DbSession, OwnerOnly
from app.core.clock import today_ist
from app.core.errors import PermissionDeniedError
from app.domain import kpi_catalogue
from app.models.enums import Role
from app.schemas.finance import (
    CashBookOut,
    CashEntryCreate,
    CashEntryOut,
    CashReverse,
    ExpenseCategoryIn,
    ExpenseCategoryOut,
    ExpenseCategoryUpdate,
    KpiDefinitionOut,
    PnlOut,
    RateOverridesOut,
)
from app.services import cashbook as service
from app.services import finance as finance_service

router = APIRouter(tags=["finance"])


@router.get("/expense-categories", response_model=list[ExpenseCategoryOut])
def list_categories(
    principal: CurrentPrincipal, db: DbSession, include_inactive: bool = False
) -> list[ExpenseCategoryOut]:
    return service.list_categories(db, include_inactive and principal.is_owner)


@router.post(
    "/expense-categories", response_model=ExpenseCategoryOut, status_code=status.HTTP_201_CREATED
)
def create_category(body: ExpenseCategoryIn, _: OwnerOnly, db: DbSession) -> ExpenseCategoryOut:
    return service.create_category(db, body)


@router.patch("/expense-categories/{category_id}", response_model=ExpenseCategoryOut)
def update_category(
    category_id: int, body: ExpenseCategoryUpdate, _: OwnerOnly, db: DbSession
) -> ExpenseCategoryOut:
    return service.update_category(db, category_id, body)


@router.get("/cash-book", response_model=CashBookOut)
def cash_book(
    principal: CurrentPrincipal,
    db: DbSession,
    location_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> CashBookOut:
    """Vouchers for a period (today by default). Counter staff see their own shop's."""
    if location_id is not None and not principal.can_access_location(location_id):
        raise PermissionDeniedError("You can only see your own shop's cash book")
    today = today_ist()
    return service.cash_book(
        db,
        location_ids=principal.location_ids if principal.role is Role.COUNTER else None,
        location_id=location_id,
        date_from=date_from or today,
        date_to=date_to or date_from or today,
    )


@router.post("/cash-book", response_model=CashEntryOut, status_code=status.HTTP_201_CREATED)
def create_entry(body: CashEntryCreate, principal: CurrentPrincipal, db: DbSession) -> CashEntryOut:
    """An expense, a bank deposit or withdrawal, or the owner's drawing or capital."""
    actor = service.Actor(
        principal.user_id, principal.role, principal.can_access_location(body.location_id)
    )
    return service.create_entry(db, body, actor)


@router.post("/cash-book/{entry_id}/reverse", response_model=CashEntryOut)
def reverse_entry(
    entry_id: int, body: CashReverse, principal: OwnerOnly, db: DbSession
) -> CashEntryOut:
    """Cancel a voucher with a new one dated today. The original is never changed."""
    return service.reverse_entry(db, entry_id, body.reason, actor_id=principal.user_id)


@router.get("/reports/pnl", response_model=PnlOut)
def profit_and_loss(
    _: OwnerOnly, db: DbSession, period: str | None = None, location_id: int | None = None
) -> PnlOut:
    """Profit and loss for a calendar month (this month by default). Owner only."""
    return finance_service.profit_and_loss(db, period or today_ist().strftime("%Y-%m"), location_id)


@router.get("/reports/rate-overrides", response_model=RateOverridesOut)
def rate_overrides(
    _: OwnerOnly, db: DbSession, period: str | None = None, location_id: int | None = None
) -> RateOverridesOut:
    """Hand-set prices by user and their rupee effect against the list rate. Owner only."""
    return finance_service.rate_overrides(db, period or today_ist().strftime("%Y-%m"), location_id)


@router.get("/kpis/definitions", response_model=list[KpiDefinitionOut])
def kpi_definitions(principal: CurrentPrincipal) -> list[KpiDefinitionOut]:
    """The metric catalogue behind every tooltip and the Metrics explained page."""
    return [
        KpiDefinitionOut(
            code=k.code,
            name=k.name,
            formula=k.formula,
            meaning=k.meaning,
            example=k.example,
            sources=k.sources,
            owner_only=k.owner_only,
            refresh=k.refresh.value,
            good=k.good.value,
            unit=k.unit,
        )
        for k in kpi_catalogue.definitions(owner=principal.is_owner)
    ]
