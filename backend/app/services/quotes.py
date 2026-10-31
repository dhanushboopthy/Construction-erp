"""Quotations (estimates) and proforma invoices. Priced, taxed and numbered like a bill, but not
a tax invoice: they move no stock and put nothing on the customer's account. One can become a
bill (`InvoiceCreate.quote_id`); the bill is a separate, real GST invoice."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import today_ist
from app.core.errors import BusinessRuleError, NotFoundError
from app.core.tenancy import current_tenant_id
from app.domain import pricing
from app.domain.fiscal import fy_label
from app.domain.money import ZERO
from app.models.enums import DocType, FulfilmentSource, QuoteKind
from app.models.sales import SalesInvoice, SalesQuote, SalesQuoteLine
from app.models.setup import Location
from app.schemas.sales import (
    InvoiceCreate,
    InvoicePreview,
    QuoteCreate,
    QuoteLineOut,
    QuoteOut,
    QuoteSummary,
)
from app.services import approvals as approval_service
from app.services import sales as sales_service
from app.services.numbering import allocate_number

SERIES = {QuoteKind.QUOTATION: DocType.QUOTATION, QuoteKind.PROFORMA: DocType.PROFORMA}


def _as_bill(data: QuoteCreate) -> InvoiceCreate:
    """The quote's lines priced as a bill from the shop: no godown, direct or weight details."""
    return InvoiceCreate(
        location_id=data.location_id,
        party_id=data.party_id,
        site_id=data.site_id,
        remark=data.remark,
        lines=[
            x.model_copy(
                update={
                    "source": FulfilmentSource.SHOP,
                    "source_location_id": None,
                    "purchase_line_id": None,
                    "slip_weight": None,
                    "weight_note": None,
                }
            )
            for x in data.lines
        ],
        approval_ids=data.approval_ids,
    )


def preview(
    db: Session, data: QuoteCreate, *, is_owner: bool, can_access: bool, actor_id: int
) -> InvoicePreview:
    return sales_service.preview(
        db, _as_bill(data), is_owner=is_owner, can_access=can_access, actor_id=actor_id, quote=True
    )


def create(
    db: Session, data: QuoteCreate, *, actor_id: int, is_owner: bool, can_access: bool
) -> SalesQuote:
    today = today_ist()
    if data.valid_until is not None and data.valid_until < today:
        raise BusinessRuleError(
            "The valid-until date is already past.", code="VALID_UNTIL_PAST", field="valid_until"
        )
    bill = _as_bill(data)
    approvals = approval_service.load_valid(db, data.approval_ids, actor_id, data.party_id)
    p = sales_service.price_invoice(
        db,
        bill,
        is_owner=is_owner,
        can_access=can_access,
        approved=frozenset(a.action for a in approvals),
        quote=True,
    )
    if p.problems:
        first = p.problems[0]
        raise BusinessRuleError(
            first.message,
            code=first.code,
            requires_owner_approval=first.approval,
            field=first.field,
        )
    number = allocate_number(
        db,
        location_id=p.location.id,
        doc_type=SERIES[data.kind],
        on=today,
        fy_start_month=p.settings.financial_year_start_month,
    )
    t = p.totals
    quote = SalesQuote(
        tenant_id=current_tenant_id(db),
        kind=data.kind,
        number=number,
        financial_year=fy_label(today, p.settings.financial_year_start_month),
        location_id=p.location.id,
        party_id=p.party.id,
        site_id=p.site.id if p.site else None,
        bill_to_name=p.party.name,
        bill_to_address=p.party.address,
        bill_to_gstin=p.party.gstin,
        ship_to_name=p.site.name if p.site else None,
        ship_to_address=p.site.address if p.site else None,
        place_of_supply=p.place_of_supply,
        supply_kind=p.kind,
        supply_type=p.supply_type,
        quote_date=today,
        valid_until=data.valid_until,
        taxable_value=t.taxable,
        cgst=t.cgst,
        sgst=t.sgst,
        igst=t.igst,
        round_off=t.round_off,
        grand_total=t.grand_total,
        remark=data.remark,
        lines=[
            SalesQuoteLine(
                tenant_id=current_tenant_id(db),
                line_no=i,
                item_id=r.item.id,
                description=r.item.name,
                hsn=r.item.hsn,
                unit=r.unit,
                quantity=r.data.quantity,
                base_qty=r.base_qty,
                base_unit=r.item.base_unit,
                rate=r.rate or ZERO,
                rate_source=r.source or pricing.RateSource.MARKET,
                rate_override_reason=(
                    (r.data.rate_override_reason or "").strip()
                    if r.source is pricing.RateSource.OVERRIDE
                    else None
                ),
                discount=r.discount,
                discount_reason=r.data.discount_reason if r.discount else None,
                taxable=r.tax.taxable if r.tax else ZERO,
                gst_rate=r.item.gst_rate,
                cgst=r.tax.cgst if r.tax else ZERO,
                sgst=r.tax.sgst if r.tax else ZERO,
                igst=r.tax.igst if r.tax else ZERO,
                line_total=r.tax.total if r.tax else ZERO,
            )
            for i, r in enumerate(p.lines, start=1)
        ],
    )
    db.add(quote)
    approval_service.mark_used(approvals, number)
    db.commit()
    return quote


def get_quote(db: Session, quote_id: int) -> SalesQuote:
    row = db.get(SalesQuote, quote_id)
    if row is None or row.tenant_id != current_tenant_id(db):
        raise NotFoundError("Quotation not found")
    return row


def list_quotes(
    db: Session,
    *,
    location_ids: frozenset[int] | None,
    kind: QuoteKind | None,
    q: str | None,
    limit: int,
    offset: int,
) -> tuple[list[SalesQuote], int]:
    filters = [SalesQuote.tenant_id == current_tenant_id(db)]
    if location_ids is not None:
        filters.append(SalesQuote.location_id.in_(location_ids))
    if kind is not None:
        filters.append(SalesQuote.kind == kind)
    if q:
        like = f"%{q.strip()}%"
        filters.append(SalesQuote.number.ilike(like) | SalesQuote.bill_to_name.ilike(like))
    total = db.execute(select(func.count()).select_from(SalesQuote).where(*filters)).scalar_one()
    rows = db.execute(
        select(SalesQuote)
        .where(*filters)
        .order_by(SalesQuote.quote_date.desc(), SalesQuote.id.desc())
        .limit(limit)
        .offset(offset)
    ).scalars()
    return list(rows), total


def summary(db: Session, row: SalesQuote) -> QuoteSummary:
    loc = db.get(Location, row.location_id)
    invoice = db.get(SalesInvoice, row.invoice_id) if row.invoice_id else None
    return QuoteSummary(
        id=row.id,
        kind=row.kind,
        number=row.number,
        quote_date=row.quote_date,
        valid_until=row.valid_until,
        party_id=row.party_id,
        party_name=row.bill_to_name,
        location_id=row.location_id,
        location_code=loc.code if loc else "",
        grand_total=row.grand_total,
        invoice_id=row.invoice_id,
        invoice_number=invoice.number if invoice else None,
    )


def view(db: Session, row: SalesQuote) -> QuoteOut:
    return QuoteOut(
        **summary(db, row).model_dump(),
        site_id=row.site_id,
        bill_to_gstin=row.bill_to_gstin,
        ship_to_name=row.ship_to_name,
        place_of_supply=row.place_of_supply,
        supply_kind=row.supply_kind,
        supply_type=row.supply_type,
        taxable_value=row.taxable_value,
        cgst=row.cgst,
        sgst=row.sgst,
        igst=row.igst,
        round_off=row.round_off,
        remark=row.remark,
        lines=[QuoteLineOut.model_validate(x) for x in row.lines],
    )
