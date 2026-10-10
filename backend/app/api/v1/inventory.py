"""Inventory analytics, replenishment, stock value (NRV) and weight shortages (FM6)."""

from datetime import date, timedelta

from fastapi import APIRouter, status

from app.api.deps import DbSession, OwnerOnly, OwnerOrAccountant
from app.core.clock import today_ist
from app.schemas.inventory import (
    FifoAgeOut,
    InventoryAnalyticsOut,
    NrvReportOut,
    ShrinkageOut,
    WritedownCreate,
    WritedownOut,
)
from app.services import inventory as service

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("/analytics", response_model=InventoryAnalyticsOut)
def analytics(_: OwnerOnly, db: DbSession) -> InventoryAnalyticsOut:
    """ABC, FSN, stock age, cover days and reorder points. Owner only (it shows stock at cost)."""
    return service.analytics(db, today_ist())


@router.get("/nrv", response_model=NrvReportOut)
def nrv(_: OwnerOrAccountant, db: DbSession) -> NrvReportOut:
    """Stock against today's market rate: the loss when it is worth less than it cost."""
    return service.nrv_report(db, today_ist())


@router.get("/writedowns", response_model=list[WritedownOut])
def list_writedowns(
    _: OwnerOrAccountant,
    db: DbSession,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[WritedownOut]:
    return service.list_writedowns(db, date_from, date_to)


@router.post("/writedowns", response_model=WritedownOut, status_code=status.HTTP_201_CREATED)
def create_writedown(body: WritedownCreate, principal: OwnerOnly, db: DbSession) -> WritedownOut:
    """Lower stock to its realisable value. Owner only; no quantity moves, no input tax is
    reversed, and the loss comes off the month's net profit."""
    return service.create_writedown(db, body, today=today_ist(), actor_id=principal.user_id)


@router.get("/fifo-age", response_model=FifoAgeOut)
def fifo_age(_: OwnerOnly, db: DbSession) -> FifoAgeOut:
    """Cement by the day it came in, assuming the oldest is sold first."""
    return service.fifo_age(db, today_ist())


@router.get("/shrinkage", response_model=ShrinkageOut)
def shrinkage(
    _: OwnerOrAccountant,
    db: DbSession,
    date_from: date | None = None,
    date_to: date | None = None,
) -> ShrinkageOut:
    """Weight shortages by supplier (billed against the weighbridge); 90 days by default."""
    end = date_to or today_ist()
    return service.shrinkage(db, date_from or end - timedelta(days=89), end)
