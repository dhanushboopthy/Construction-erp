from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentPrincipal, DbSession, OwnerOrCounter
from app.core.errors import NotFoundError
from app.models.enums import QuoteKind, Role
from app.schemas.common import Page
from app.schemas.sales import InvoicePreview, QuoteCreate, QuoteOut, QuoteSummary
from app.services import invoice_pdf
from app.services import quotes as quote_service

router = APIRouter(prefix="/quotes", tags=["quotes"])


@router.post("/preview", response_model=InvoicePreview)
def preview_quote(body: QuoteCreate, principal: OwnerOrCounter, db: DbSession) -> InvoicePreview:
    """Prices and tax for a quotation or proforma being keyed. No stock or credit checks."""
    return quote_service.preview(
        db,
        body,
        is_owner=principal.is_owner,
        can_access=principal.can_access_location(body.location_id),
        actor_id=principal.user_id,
    )


@router.post("", response_model=QuoteOut, status_code=status.HTTP_201_CREATED)
def create_quote(body: QuoteCreate, principal: OwnerOrCounter, db: DbSession) -> QuoteOut:
    """Save a quotation or proforma invoice. It moves no stock and owes nothing."""
    row = quote_service.create(
        db,
        body,
        actor_id=principal.user_id,
        is_owner=principal.is_owner,
        can_access=principal.can_access_location(body.location_id),
    )
    return quote_service.view(db, row)


@router.get("", response_model=Page[QuoteSummary])
def list_quotes(
    principal: CurrentPrincipal,
    db: DbSession,
    kind: QuoteKind | None = None,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[QuoteSummary]:
    scope = principal.location_ids if principal.role is Role.COUNTER else None
    rows, total = quote_service.list_quotes(
        db, location_ids=scope, kind=kind, q=q, limit=limit, offset=offset
    )
    return Page[QuoteSummary](
        items=[quote_service.summary(db, r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/{quote_id}", response_model=QuoteOut)
def get_quote(quote_id: int, principal: CurrentPrincipal, db: DbSession) -> QuoteOut:
    row = quote_service.get_quote(db, quote_id)
    if not principal.can_access_location(row.location_id):
        raise NotFoundError("Quotation not found")
    return quote_service.view(db, row)


@router.get("/{quote_id}/pdf", response_class=Response)
def quote_pdf_file(quote_id: int, principal: CurrentPrincipal, db: DbSession) -> Response:
    row = quote_service.get_quote(db, quote_id)
    if not principal.can_access_location(row.location_id):
        raise NotFoundError("Quotation not found")
    return Response(
        invoice_pdf.render_quote(db, row),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{row.number.replace("/", "-")}.pdf"'},
    )
