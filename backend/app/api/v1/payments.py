from typing import Annotated

from fastapi import APIRouter, Header, Response, status

from app.api.deps import CurrentPrincipal, DbSession, OwnerOrCounter
from app.core.errors import PermissionDeniedError
from app.models.enums import LedgerAccount, Role
from app.schemas.ledger import OpenBillsOut
from app.schemas.purchases import PaymentCreate, PaymentOut
from app.services import payments as payment_service

router = APIRouter(tags=["payments"])


@router.post("/payments", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
def create_payment(
    body: PaymentCreate,
    principal: OwnerOrCounter,
    db: DbSession,
    response: Response,
    idempotency_key: Annotated[str | None, Header(max_length=80)] = None,
) -> PaymentOut:
    """Record money received from a customer (owner, counter at own shop) or paid to a supplier
    (owner). Bills you pick are paid first; the rest goes oldest first. A repeated
    Idempotency-Key returns the first payment."""
    payment, created = payment_service.create_payment(
        db,
        body,
        actor_id=principal.user_id,
        is_owner=principal.is_owner,
        can_access=principal.can_access_location(body.location_id),
        idempotency_key=idempotency_key,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return payment


@router.get("/payments", response_model=list[PaymentOut])
def list_payments(
    principal: CurrentPrincipal, db: DbSession, party_id: int | None = None
) -> list[PaymentOut]:
    scope = principal.location_ids if principal.role is Role.COUNTER else None
    return payment_service.list_payments(db, party_id, scope)


@router.get("/parties/{party_id}/open-bills", response_model=OpenBillsOut)
def open_bills(
    party_id: int, principal: CurrentPrincipal, db: DbSession, account: LedgerAccount
) -> OpenBillsOut:
    """Unpaid bills to choose from when recording a payment."""
    if account is LedgerAccount.PAYABLE and principal.role is Role.COUNTER:
        raise PermissionDeniedError("Supplier payables are for the owner and accountant")
    return payment_service.open_bills_view(db, party_id, account)
