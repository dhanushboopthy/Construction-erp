from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentPrincipal, DbSession, OwnerOnly, OwnerOrAccountant, OwnerOrCounter
from app.core.errors import NotFoundError
from app.models.enums import Role
from app.schemas.common import Page
from app.schemas.returns import (
    CreditNoteCreate,
    CreditNoteOut,
    CreditNoteSummary,
    DebitNoteCreate,
    DebitNoteOut,
    DebitNoteSummary,
)
from app.services import note_pdf
from app.services import returns as return_service

credit_router = APIRouter(prefix="/credit-notes", tags=["returns"])
debit_router = APIRouter(prefix="/debit-notes", tags=["returns"])


def _pdf(data: bytes, number: str) -> Response:
    return Response(
        data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{number.replace("/", "-")}.pdf"'},
    )


@credit_router.post("", response_model=CreditNoteOut, status_code=status.HTTP_201_CREATED)
def create_credit_note(
    body: CreditNoteCreate, principal: OwnerOrCounter, db: DbSession
) -> CreditNoteOut:
    """Take back goods from a bill. Inside the return window it needs no approval (B11)."""
    note = return_service.create_credit_note(
        db,
        body,
        actor_id=principal.user_id,
        is_owner=principal.is_owner,
        can_access=principal.can_access_location,
    )
    return return_service.credit_view(db, note)


@credit_router.get("", response_model=Page[CreditNoteSummary])
def list_credit_notes(
    principal: CurrentPrincipal,
    db: DbSession,
    invoice_id: int | None = None,
    party_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[CreditNoteSummary]:
    scope = principal.location_ids if principal.role is Role.COUNTER else None
    rows, total = return_service.list_credit_notes(
        db, location_ids=scope, invoice_id=invoice_id, party_id=party_id, limit=limit, offset=offset
    )
    return Page[CreditNoteSummary](
        items=[return_service.credit_summary(db, r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@credit_router.get("/{note_id}", response_model=CreditNoteOut)
def get_credit_note(note_id: int, principal: CurrentPrincipal, db: DbSession) -> CreditNoteOut:
    note = return_service.get_credit_note(db, note_id)
    if not principal.can_access_location(note.location_id):
        raise NotFoundError("Credit note not found")
    return return_service.credit_view(db, note)


@credit_router.get("/{note_id}/pdf", response_class=Response)
def credit_note_pdf(note_id: int, principal: CurrentPrincipal, db: DbSession) -> Response:
    note = return_service.get_credit_note(db, note_id)
    if not principal.can_access_location(note.location_id):
        raise NotFoundError("Credit note not found")
    return _pdf(note_pdf.credit_note_pdf(db, note), note.number)


@debit_router.post("", response_model=DebitNoteOut, status_code=status.HTTP_201_CREATED)
def create_debit_note(body: DebitNoteCreate, principal: OwnerOnly, db: DbSession) -> DebitNoteOut:
    """Send goods back to a supplier: stock goes out at its landed cost, the payable falls."""
    note = return_service.create_debit_note(db, body, actor_id=principal.user_id)
    return return_service.debit_view(db, note)


@debit_router.get("", response_model=Page[DebitNoteSummary])
def list_debit_notes(
    principal: OwnerOrAccountant,
    db: DbSession,
    purchase_id: int | None = None,
    party_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[DebitNoteSummary]:
    rows, total = return_service.list_debit_notes(
        db, purchase_id=purchase_id, party_id=party_id, limit=limit, offset=offset
    )
    return Page[DebitNoteSummary](
        items=[return_service.debit_summary(db, r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@debit_router.get("/{note_id}", response_model=DebitNoteOut)
def get_debit_note(note_id: int, principal: OwnerOrAccountant, db: DbSession) -> DebitNoteOut:
    return return_service.debit_view(db, return_service.get_debit_note(db, note_id))


@debit_router.get("/{note_id}/pdf", response_class=Response)
def debit_note_pdf(note_id: int, principal: OwnerOrAccountant, db: DbSession) -> Response:
    note = return_service.get_debit_note(db, note_id)
    return _pdf(note_pdf.debit_note_pdf(db, note), note.number)
