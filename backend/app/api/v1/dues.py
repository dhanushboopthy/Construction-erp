from fastapi import APIRouter

from app.api.deps import CurrentPrincipal, DbSession
from app.core.clock import today_ist
from app.core.errors import PermissionDeniedError
from app.models.enums import LedgerAccount, Role
from app.schemas.ledger import DuesOut, StatementOut
from app.services import ledgers

router = APIRouter(tags=["ledger"])


@router.get("/parties/{party_id}/statement", response_model=StatementOut)
def party_statement(
    party_id: int, principal: CurrentPrincipal, db: DbSession, site_id: int | None = None
) -> StatementOut:
    """A customer's statement, per site when `site_id` is given (B9). What we owe a supplier is
    shown to the owner and accountant only."""
    return ledgers.party_statement(
        db,
        party_id,
        site_id=site_id,
        today=today_ist(),
        see_payable=principal.role is not Role.COUNTER,
    )


@router.get("/reports/dues", response_model=DuesOut)
def dues(principal: CurrentPrincipal, db: DbSession, account: LedgerAccount) -> DuesOut:
    if account is LedgerAccount.PAYABLE and principal.role is Role.COUNTER:
        raise PermissionDeniedError("Supplier payables are for the owner and accountant")
    return ledgers.dues_report(db, account, today_ist())
