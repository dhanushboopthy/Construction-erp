"""Controls (FM7): the period lock, bank statements and reconciliation, the exception report."""

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile, status

from app.api.deps import DbSession, OwnerOnly, OwnerOrAccountant
from app.core.clock import today_ist
from app.core.config import get_settings
from app.schemas.controls import (
    BankAccountCreate,
    BankAccountOut,
    BankAccountUpdate,
    BankStatementOut,
    ExceptionReport,
    PeriodChecklist,
    PeriodLockOut,
    PeriodLockSet,
    ReconciliationOut,
)
from app.services import banking, exceptions, period_lock

router = APIRouter(tags=["controls"])


@router.get("/period-lock", response_model=PeriodLockOut)
def get_period_lock(_: OwnerOrAccountant, db: DbSession) -> PeriodLockOut:
    return period_lock.get_lock(db)


@router.put("/period-lock", response_model=PeriodLockOut)
def set_period_lock(body: PeriodLockSet, principal: OwnerOnly, db: DbSession) -> PeriodLockOut:
    """Lock the books through a date, or reopen them. A reason is always recorded."""
    return period_lock.set_lock(db, body, actor_id=principal.user_id)


@router.get("/period-lock/checklist", response_model=PeriodChecklist)
def month_end_checklist(_: OwnerOrAccountant, db: DbSession, period: str) -> PeriodChecklist:
    return period_lock.checklist(db, period)


@router.get("/bank/accounts", response_model=list[BankAccountOut])
def list_bank_accounts(_: OwnerOrAccountant, db: DbSession) -> list[BankAccountOut]:
    return banking.list_accounts(db)


@router.post("/bank/accounts", response_model=BankAccountOut, status_code=status.HTTP_201_CREATED)
def create_bank_account(
    body: BankAccountCreate, principal: OwnerOnly, db: DbSession
) -> BankAccountOut:
    return banking.create_account(db, body, actor_id=principal.user_id)


@router.patch("/bank/accounts/{account_id}", response_model=BankAccountOut)
def update_bank_account(
    account_id: int, body: BankAccountUpdate, principal: OwnerOnly, db: DbSession
) -> BankAccountOut:
    return banking.update_account(db, account_id, body, actor_id=principal.user_id)


@router.get("/bank/statements", response_model=list[BankStatementOut])
def list_statements(_: OwnerOrAccountant, db: DbSession) -> list[BankStatementOut]:
    return banking.list_statements(db)


@router.post(
    "/bank/statements", response_model=BankStatementOut, status_code=status.HTTP_201_CREATED
)
def import_statement(
    principal: OwnerOrAccountant,
    db: DbSession,
    bank_account_id: Annotated[int, Form()],
    file: Annotated[UploadFile, File()],
) -> BankStatementOut:
    """Upload a bank's CSV. Rows already imported from an overlapping file are skipped; a file
    with any unreadable row is refused whole."""
    limit = get_settings().max_upload_mb * 1024 * 1024
    return banking.import_statement(
        db,
        bank_account_id,
        file.filename or "statement.csv",
        file.file.read(limit + 1)[:limit],
        actor_id=principal.user_id,
    )


@router.get("/bank/reconciliation", response_model=ReconciliationOut)
def reconciliation(
    _: OwnerOrAccountant,
    db: DbSession,
    date_from: date | None = None,
    date_to: date | None = None,
    bank_account_id: int | None = None,
) -> ReconciliationOut:
    """Bank lines matched to receipts and payments, with what is left over on each side."""
    end = date_to or today_ist()
    return banking.reconciliation(db, date_from or end - timedelta(days=30), end, bank_account_id)


@router.get("/reports/exceptions", response_model=ExceptionReport)
def exception_report(
    _: OwnerOnly, db: DbSession, date_from: date | None = None, date_to: date | None = None
) -> ExceptionReport:
    """Entries that look like the usual ways money or stock goes missing (owner only)."""
    end = date_to or today_ist()
    return exceptions.exception_report(db, date_from or end - timedelta(days=29), end)
