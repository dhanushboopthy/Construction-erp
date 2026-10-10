"""Receivables by due date, bad-debt write-offs and working capital (FM5)."""

from datetime import date

from fastapi import APIRouter, status

from app.api.deps import DbSession, OwnerOnly, OwnerOrAccountant
from app.core.clock import today_ist
from app.schemas.finance import WorkingCapitalOut
from app.schemas.receivables import (
    ReceivablesOut,
    ReceivablesOwnerOut,
    WriteoffCreate,
    WriteoffOut,
)
from app.services import receivables as service
from app.services import working_capital as wc_service

router = APIRouter(tags=["receivables"])


@router.get("/reports/receivables", response_model=ReceivablesOut | ReceivablesOwnerOut)
def receivables(principal: OwnerOrAccountant, db: DbSession) -> ReceivablesOut:
    """What customers owe, aged from each bill's due date. The provision for doubtful debts is
    shown to the owner only."""
    return service.receivables_report(db, today_ist(), owner=principal.is_owner)


@router.get("/reports/working-capital", response_model=WorkingCapitalOut)
def working_capital(
    _: OwnerOnly, db: DbSession, period: str | None = None, trend: bool = True
) -> WorkingCapitalOut:
    """DIO, DSO, DPO, advance days, cash conversion cycle and cash tied up for a month."""
    return wc_service.working_capital(db, period or today_ist().strftime("%Y-%m"), with_trend=trend)


@router.get("/write-offs", response_model=list[WriteoffOut])
def list_writeoffs(
    _: OwnerOrAccountant,
    db: DbSession,
    party_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[WriteoffOut]:
    return service.list_writeoffs(db, party_id=party_id, date_from=date_from, date_to=date_to)


@router.post("/write-offs", response_model=WriteoffOut, status_code=status.HTTP_201_CREATED)
def create_writeoff(body: WriteoffCreate, principal: OwnerOnly, db: DbSession) -> WriteoffOut:
    """Give up on money a customer owes. Owner only; no GST effect; the customer's account is
    credited and the debt is a loss in the month's profit."""
    return service.create_writeoff(db, body, actor_id=principal.user_id)
