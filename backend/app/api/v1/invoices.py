from datetime import date
from typing import Annotated

from fastapi import APIRouter, Header, Query, Response, status

from app.api.deps import CurrentPrincipal, DbSession, OwnerOrCounter
from app.core.errors import NotFoundError
from app.models.enums import Role
from app.schemas.common import Page
from app.schemas.sales import (
    InvoiceCreate,
    InvoiceOut,
    InvoiceOwnerOut,
    InvoicePreview,
    InvoiceSummary,
)
from app.services import invoice_pdf
from app.services import sales as sales_service

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.post("/preview", response_model=InvoicePreview)
def preview_invoice(
    body: InvoiceCreate, principal: OwnerOrCounter, db: DbSession
) -> InvoicePreview:
    """Prices, tax, stock and totals for a bill being keyed. Nothing is saved, no cost is shown."""
    return sales_service.preview(
        db,
        body,
        is_owner=principal.is_owner,
        can_access=principal.can_access_location(body.location_id),
        actor_id=principal.user_id,
    )


@router.post("", response_model=InvoiceOwnerOut | InvoiceOut, status_code=status.HTTP_201_CREATED)
def create_invoice(
    body: InvoiceCreate,
    principal: OwnerOrCounter,
    db: DbSession,
    response: Response,
    idempotency_key: Annotated[str | None, Header(max_length=80)] = None,
) -> InvoiceOwnerOut | InvoiceOut:
    """Save the bill. A repeated Idempotency-Key returns the first bill instead of a second."""
    invoice, created = sales_service.create(
        db,
        body,
        actor_id=principal.user_id,
        is_owner=principal.is_owner,
        can_access=principal.can_access_location(body.location_id),
        idempotency_key=idempotency_key,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return sales_service.invoice_view(db, invoice, principal.sees_cost)


@router.get("", response_model=Page[InvoiceSummary])
def list_invoices(
    principal: CurrentPrincipal,
    db: DbSession,
    party_id: int | None = None,
    q: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[InvoiceSummary]:
    scope = principal.location_ids if principal.role is Role.COUNTER else None
    rows, total = sales_service.list_invoices(
        db,
        location_ids=scope,
        party_id=party_id,
        q=q,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return Page[InvoiceSummary](
        items=[sales_service.summary(db, r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/{invoice_id}", response_model=InvoiceOwnerOut | InvoiceOut)
def get_invoice(
    invoice_id: int, principal: CurrentPrincipal, db: DbSession
) -> InvoiceOwnerOut | InvoiceOut:
    invoice = sales_service.get_invoice(db, invoice_id)
    if not principal.can_access_location(invoice.location_id):
        raise NotFoundError("Invoice not found")
    return sales_service.invoice_view(db, invoice, principal.sees_cost)


@router.get("/{invoice_id}/pdf", response_class=Response)
def invoice_pdf_file(
    invoice_id: int, principal: CurrentPrincipal, db: DbSession, copy: str = "original"
) -> Response:
    """A4 tax invoice. `copy` is original, duplicate or triplicate (printed in the corner)."""
    invoice = sales_service.get_invoice(db, invoice_id)
    if not principal.can_access_location(invoice.location_id):
        raise NotFoundError("Invoice not found")
    label = {
        "original": "Original for recipient",
        "duplicate": "Duplicate for transporter",
        "triplicate": "Triplicate for supplier",
    }.get(copy, "Original for recipient")
    pdf = invoice_pdf.DEFAULT_RENDERER.render(db, invoice, copy_label=label, eway_no=None)
    return Response(
        pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{invoice.number.replace("/", "-")}.pdf"'
        },
    )
