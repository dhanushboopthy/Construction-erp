from datetime import date

from fastapi import APIRouter, status

from app.api.deps import CurrentPrincipal, DbSession, OwnerOnly
from app.core.clock import today_ist
from app.schemas.rates import (
    CustomerRateCreate,
    CustomerRateOut,
    CustomerRateUpdate,
    HistoryPoint,
    MarginOut,
    MarginPut,
    MarketRatesPut,
    MarketRatesResult,
    RateRowOut,
    RateRowOwnerOut,
    ResolvedPriceOut,
)
from app.services import rates as rate_service

router = APIRouter(tags=["rates"])


@router.get("/rates/market", response_model=list[RateRowOwnerOut] | list[RateRowOut])
def rate_board(
    principal: CurrentPrincipal, db: DbSession, on: date | None = None
) -> list[RateRowOwnerOut] | list[RateRowOut]:
    """Today's selling rate for every item. The owner also gets cost, margin and a suggestion."""
    return rate_service.rate_board(db, on or today_ist(), owner=principal.sees_cost)


@router.put("/rates/market", response_model=MarketRatesResult)
def put_market_rates(body: MarketRatesPut, _: OwnerOnly, db: DbSession) -> MarketRatesResult:
    return rate_service.put_market_rates(db, body)


@router.get("/rates/market/{item_id}/history", response_model=list[HistoryPoint])
def rate_history(item_id: int, _: CurrentPrincipal, db: DbSession) -> list[HistoryPoint]:
    return rate_service.rate_history(db, item_id)


@router.get("/rates/resolve", response_model=ResolvedPriceOut)
def resolve_price(
    _: CurrentPrincipal,
    db: DbSession,
    item_id: int,
    party_id: int | None = None,
    on: date | None = None,
) -> ResolvedPriceOut:
    """The rate a bill would use: the customer's own rate, else the latest market rate."""
    return rate_service.resolve(db, item_id, party_id, on or today_ist())


@router.get("/customer-rates", response_model=list[CustomerRateOut])
def list_customer_rates(
    _: OwnerOnly, db: DbSession, party_id: int | None = None, item_id: int | None = None
) -> list[CustomerRateOut]:
    return rate_service.list_customer_rates(db, party_id, item_id)


@router.post("/customer-rates", response_model=CustomerRateOut, status_code=status.HTTP_201_CREATED)
def create_customer_rate(body: CustomerRateCreate, _: OwnerOnly, db: DbSession) -> CustomerRateOut:
    return rate_service.create_customer_rate(db, body)


@router.patch("/customer-rates/{rate_id}", response_model=CustomerRateOut)
def update_customer_rate(
    rate_id: int, body: CustomerRateUpdate, _: OwnerOnly, db: DbSession
) -> CustomerRateOut:
    return rate_service.update_customer_rate(db, rate_id, body)


@router.get("/margins", response_model=list[MarginOut])
def list_margins(_: OwnerOnly, db: DbSession) -> list[MarginOut]:
    return rate_service.list_margins(db)


@router.put("/margins", response_model=list[MarginOut])
def put_margins(body: list[MarginPut], _: OwnerOnly, db: DbSession) -> list[MarginOut]:
    return rate_service.put_margins(db, body)
