"""Returns (Milestone 8, rules B11 and B13): credit notes for goods a customer brings back and
debit notes for goods sent back to a supplier. Both reverse part of an issued bill pro rata,
move stock and the party's balance in the same transaction, and are never edited or deleted."""

from collections.abc import Callable
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import today_ist
from app.core.errors import BusinessRuleError, NotFoundError
from app.core.tenancy import TENANT_ID
from app.domain import gst
from app.domain import returns as return_rules
from app.domain.compliance import return_window_open
from app.domain.fiscal import fy_label
from app.domain.money import ZERO, qty
from app.domain.stock_valuation import NegativeStockError, ensure_available
from app.models.enums import (
    ApprovalAction,
    DocType,
    LedgerAccount,
    PartyRef,
    PurchaseMode,
    StockRef,
)
from app.models.masters import Item, Party
from app.models.purchasing import Purchase, PurchaseLine
from app.models.returns import CreditNote, CreditNoteLine, DebitNote, DebitNoteLine
from app.models.sales import SalesInvoice, SalesLine
from app.models.setup import Location
from app.schemas.returns import (
    CreditNoteCreate,
    CreditNoteLineOut,
    CreditNoteOut,
    CreditNoteSummary,
    DebitNoteCreate,
    DebitNoteLineOut,
    DebitNoteOut,
    DebitNoteSummary,
    ReturnLineIn,
)
from app.services import approvals as approval_service
from app.services import ledgers
from app.services.numbering import allocate_number
from app.services.shop_settings import get_settings_row

# ---------------------------------------------------------------------------- helpers


def _base_returned(line_quantity: Decimal, line_base_qty: Decimal, asked: Decimal) -> Decimal:
    """Convert a quantity in the line's own unit to base units (exact when it is the whole line)."""
    if asked == line_quantity:
        return line_base_qty
    return qty(line_base_qty * asked / line_quantity)


def _check(sold: Decimal, done: Decimal, wanted: Decimal, field: str) -> None:
    try:
        return_rules.check_returnable(sold, done, wanted)
    except ValueError as exc:
        raise BusinessRuleError(str(exc), code="RETURN_TOO_MUCH", field=field) from exc


def _no_repeats(lines: list[ReturnLineIn]) -> None:
    ids = [x.line_id for x in lines]
    if len(set(ids)) != len(ids):
        raise BusinessRuleError(
            "A line is listed twice. Combine the quantity into one row.",
            code="RETURN_LINE_REPEATED",
            field="lines",
        )


# ---------------------------------------------------------------------------- credit notes


def returned_on_invoice(db: Session, invoice_id: int) -> dict[int, Decimal]:
    rows = db.execute(
        select(CreditNoteLine.sales_line_id, func.sum(CreditNoteLine.base_qty))
        .join(CreditNote, CreditNote.id == CreditNoteLine.credit_note_id)
        .where(CreditNote.invoice_id == invoice_id)
        .group_by(CreditNoteLine.sales_line_id)
    ).all()
    return dict(rows)


def create_credit_note(
    db: Session,
    data: CreditNoteCreate,
    *,
    actor_id: int,
    is_owner: bool,
    can_access: Callable[[int], bool],
) -> CreditNote:
    invoice = db.get(SalesInvoice, data.invoice_id)
    if invoice is None or invoice.tenant_id != TENANT_ID or not can_access(invoice.location_id):
        raise NotFoundError("Invoice not found", field="invoice_id")
    _no_repeats(data.lines)
    today = today_ist()
    settings = get_settings_row(db)

    approvals = approval_service.load_valid(db, data.approval_ids, actor_id, invoice.party_id)
    approved_late = any(a.action is ApprovalAction.LATE_RETURN for a in approvals)
    in_window = return_window_open(invoice.invoice_date, today, settings.return_window_days)
    if not (in_window or is_owner or approved_late):
        raise BusinessRuleError(
            f"This bill is older than {settings.return_window_days} days. "
            "A return now needs the owner's approval.",
            code="RETURN_WINDOW_CLOSED",
            requires_owner_approval=True,
        )

    ledgers.lock_items(db, {x.item_id for x in invoice.lines})
    ledgers.lock_party(db, invoice.party_id)
    done = returned_on_invoice(db, invoice.id)
    by_id = {x.id: x for x in invoice.lines}

    priced: list[tuple[SalesLine, Decimal, Decimal, gst.LineTax]] = []
    for i, asked in enumerate(data.lines):
        line = by_id.get(asked.line_id)
        if line is None:
            raise NotFoundError("That line is not on this invoice", field=f"lines[{i}].line_id")
        base = _base_returned(line.quantity, line.base_qty, asked.quantity)
        _check(line.base_qty, done.get(line.id, ZERO), base, f"lines[{i}].quantity")
        taxable = return_rules.returned_taxable(line.taxable, line.base_qty, base)
        priced.append(
            (line, base, taxable, gst.line_tax(taxable, line.gst_rate, invoice.supply_kind))
        )
    totals = gst.invoice_totals([p[3] for p in priced])

    number = allocate_number(
        db,
        location_id=invoice.location_id,
        doc_type=DocType.CREDIT_NOTE,
        on=today,
        fy_start_month=settings.financial_year_start_month,
    )
    approver = next(
        (a.approved_by for a in approvals if a.action is ApprovalAction.LATE_RETURN), None
    )
    note = CreditNote(
        tenant_id=TENANT_ID,
        number=number,
        financial_year=fy_label(today, settings.financial_year_start_month),
        location_id=invoice.location_id,
        invoice_id=invoice.id,
        party_id=invoice.party_id,
        site_id=invoice.site_id,
        note_date=today,
        reason=data.reason,
        bill_to_name=invoice.bill_to_name,
        bill_to_address=invoice.bill_to_address,
        bill_to_gstin=invoice.bill_to_gstin,
        place_of_supply=invoice.place_of_supply,
        supply_kind=invoice.supply_kind,
        supply_type=invoice.supply_type,
        taxable_value=totals.taxable,
        cgst=totals.cgst,
        sgst=totals.sgst,
        igst=totals.igst,
        round_off=totals.round_off,
        grand_total=totals.grand_total,
        approved_by=approver if approver is not None else (actor_id if is_owner else None),
        lines=[
            CreditNoteLine(
                tenant_id=TENANT_ID,
                line_no=n,
                sales_line_id=line.id,
                item_id=line.item_id,
                description=line.description,
                hsn=line.hsn,
                base_qty=base,
                base_unit=line.base_unit,
                rate=line.rate,
                taxable=tax.taxable,
                gst_rate=line.gst_rate,
                cgst=tax.cgst,
                sgst=tax.sgst,
                igst=tax.igst,
                line_total=tax.total,
                restocked_at=line.source_location_id,
            )
            for n, (line, base, _t, tax) in enumerate(priced, start=1)
        ],
    )
    db.add(note)
    db.flush()
    for row in note.lines:
        if row.restocked_at is None:
            continue  # delivered straight from a supplier: nothing was in our stock
        sold = by_id[row.sales_line_id]
        ledgers.add_stock_move(
            db,
            item_id=row.item_id,
            location_id=row.restocked_at,
            entry_date=today,
            qty_in=row.base_qty,
            unit_cost=sold.cost_per_unit,  # back in at the cost it left at
            ref_type=StockRef.SALE_RETURN,
            ref_id=note.id,
            narration=f"Credit note {number}",
            actor_id=actor_id,
        )
    ledgers.add_party_entry(
        db,
        party_id=invoice.party_id,
        site_id=invoice.site_id,
        account=LedgerAccount.RECEIVABLE,
        entry_date=today,
        ref_type=PartyRef.CREDIT_NOTE,
        ref_id=note.id,
        doc_no=number,
        applies_to=invoice.number,
        credit=totals.grand_total,
        narration=f"Credit note {number} against {invoice.number}",
        actor_id=actor_id,
    )
    approval_service.mark_used(approvals, number)
    db.commit()
    return note


def get_credit_note(db: Session, note_id: int) -> CreditNote:
    row = db.get(CreditNote, note_id)
    if row is None or row.tenant_id != TENANT_ID:
        raise NotFoundError("Credit note not found")
    return row


def list_credit_notes(
    db: Session,
    *,
    location_ids: frozenset[int] | None,
    invoice_id: int | None,
    party_id: int | None,
    limit: int,
    offset: int,
) -> tuple[list[CreditNote], int]:
    filters = [CreditNote.tenant_id == TENANT_ID]
    if location_ids is not None:
        filters.append(CreditNote.location_id.in_(location_ids))
    if invoice_id is not None:
        filters.append(CreditNote.invoice_id == invoice_id)
    if party_id is not None:
        filters.append(CreditNote.party_id == party_id)
    total = db.execute(select(func.count()).select_from(CreditNote).where(*filters)).scalar_one()
    rows = db.execute(
        select(CreditNote)
        .where(*filters)
        .order_by(CreditNote.note_date.desc(), CreditNote.id.desc())
        .limit(limit)
        .offset(offset)
    ).scalars()
    return list(rows), total


def credit_summary(db: Session, note: CreditNote) -> CreditNoteSummary:
    loc = db.get(Location, note.location_id)
    invoice = db.get(SalesInvoice, note.invoice_id)
    return CreditNoteSummary(
        id=note.id,
        number=note.number,
        note_date=note.note_date,
        party_id=note.party_id,
        party_name=note.bill_to_name,
        location_id=note.location_id,
        location_code=loc.code if loc else "",
        reason=note.reason,
        grand_total=note.grand_total,
        invoice_id=note.invoice_id,
        invoice_number=invoice.number if invoice else "",
    )


def credit_view(db: Session, note: CreditNote) -> CreditNoteOut:
    return CreditNoteOut(
        **credit_summary(db, note).model_dump(),
        financial_year=note.financial_year,
        site_id=note.site_id,
        bill_to_gstin=note.bill_to_gstin,
        place_of_supply=note.place_of_supply,
        supply_kind=note.supply_kind,
        supply_type=note.supply_type,
        taxable_value=note.taxable_value,
        cgst=note.cgst,
        sgst=note.sgst,
        igst=note.igst,
        round_off=note.round_off,
        approved_by=note.approved_by,
        lines=[CreditNoteLineOut.model_validate(x) for x in note.lines],
    )


# ---------------------------------------------------------------------------- debit notes


def returned_on_purchase(db: Session, purchase_id: int) -> dict[int, Decimal]:
    rows = db.execute(
        select(DebitNoteLine.purchase_line_id, func.sum(DebitNoteLine.base_qty))
        .join(DebitNote, DebitNote.id == DebitNoteLine.debit_note_id)
        .where(DebitNote.purchase_id == purchase_id)
        .group_by(DebitNoteLine.purchase_line_id)
    ).all()
    return dict(rows)


def create_debit_note(db: Session, data: DebitNoteCreate, *, actor_id: int) -> DebitNote:
    purchase = db.get(Purchase, data.purchase_id)
    if purchase is None or purchase.tenant_id != TENANT_ID:
        raise NotFoundError("Purchase not found", field="purchase_id")
    supplier = db.get(Party, purchase.supplier_id)
    if supplier is None:
        raise NotFoundError("Supplier not found", field="purchase_id")
    _no_repeats(data.lines)
    today = today_ist()
    settings = get_settings_row(db)
    kind = gst.supply_kind(supplier.state_code, settings.state_code)

    ledgers.lock_items(db, {x.item_id for x in purchase.lines})
    ledgers.lock_party(db, supplier.id)
    done = returned_on_purchase(db, purchase.id)
    by_id: dict[int, PurchaseLine] = {x.id: x for x in purchase.lines}
    items = {
        x.id: x
        for x in db.scalars(select(Item).where(Item.id.in_({x.item_id for x in purchase.lines})))
    }

    priced: list[tuple[PurchaseLine, Decimal, gst.LineTax]] = []
    for i, asked in enumerate(data.lines):
        line = by_id.get(asked.line_id)
        if line is None:
            raise NotFoundError("That line is not on this purchase", field=f"lines[{i}].line_id")
        base = _base_returned(line.quantity, line.billed_qty, asked.quantity)
        _check(line.billed_qty, done.get(line.id, ZERO), base, f"lines[{i}].quantity")
        taxable = return_rules.returned_taxable(line.goods_value, line.billed_qty, base)
        priced.append((line, base, gst.line_tax(taxable, line.gst_rate, kind)))
    totals = gst.invoice_totals([p[2] for p in priced])

    if purchase.mode is PurchaseMode.STOCK:  # B13: cannot send back goods that are no longer here
        for line, base, _tax in priced:
            _position, here = ledgers.stock_position(db, line.item_id, purchase.location_id)
            try:
                ensure_available(here, base)
            except NegativeStockError as exc:
                raise BusinessRuleError(
                    f"{items[line.item_id].name}: {exc}", code="INSUFFICIENT_STOCK"
                ) from exc

    number = allocate_number(
        db,
        location_id=purchase.location_id,
        doc_type=DocType.DEBIT_NOTE,
        on=today,
        fy_start_month=settings.financial_year_start_month,
    )
    note = DebitNote(
        tenant_id=TENANT_ID,
        number=number,
        financial_year=fy_label(today, settings.financial_year_start_month),
        location_id=purchase.location_id,
        purchase_id=purchase.id,
        party_id=supplier.id,
        note_date=today,
        reason=data.reason,
        supply_kind=kind,
        taxable_value=totals.taxable,
        cgst=totals.cgst,
        sgst=totals.sgst,
        igst=totals.igst,
        round_off=totals.round_off,
        grand_total=totals.grand_total,
        lines=[
            DebitNoteLine(
                tenant_id=TENANT_ID,
                line_no=n,
                purchase_line_id=line.id,
                item_id=line.item_id,
                description=items[line.item_id].name,
                hsn=items[line.item_id].hsn,
                base_qty=base,
                base_unit=items[line.item_id].base_unit,
                taxable=tax.taxable,
                gst_rate=line.gst_rate,
                cgst=tax.cgst,
                sgst=tax.sgst,
                igst=tax.igst,
                line_total=tax.total,
            )
            for n, (line, base, tax) in enumerate(priced, start=1)
        ],
    )
    db.add(note)
    db.flush()
    if purchase.mode is PurchaseMode.STOCK:
        for row, (line, _base, _tax) in zip(note.lines, priced, strict=True):
            ledgers.add_stock_move(
                db,
                item_id=row.item_id,
                location_id=purchase.location_id,
                entry_date=today,
                qty_out=row.base_qty,
                unit_cost=line.unit_cost,  # leaves at the cost it came in at
                ref_type=StockRef.PURCHASE_RETURN,
                ref_id=note.id,
                narration=f"Debit note {number}",
                actor_id=actor_id,
            )
    ledgers.add_party_entry(
        db,
        party_id=supplier.id,
        site_id=None,
        account=LedgerAccount.PAYABLE,
        entry_date=today,
        ref_type=PartyRef.DEBIT_NOTE,
        ref_id=note.id,
        doc_no=number,
        applies_to=purchase.number,
        debit=totals.grand_total,
        narration=f"Debit note {number} against {purchase.number}",
        actor_id=actor_id,
    )
    db.commit()
    return note


def get_debit_note(db: Session, note_id: int) -> DebitNote:
    row = db.get(DebitNote, note_id)
    if row is None or row.tenant_id != TENANT_ID:
        raise NotFoundError("Debit note not found")
    return row


def list_debit_notes(
    db: Session, *, purchase_id: int | None, party_id: int | None, limit: int, offset: int
) -> tuple[list[DebitNote], int]:
    filters = [DebitNote.tenant_id == TENANT_ID]
    if purchase_id is not None:
        filters.append(DebitNote.purchase_id == purchase_id)
    if party_id is not None:
        filters.append(DebitNote.party_id == party_id)
    total = db.execute(select(func.count()).select_from(DebitNote).where(*filters)).scalar_one()
    rows = db.execute(
        select(DebitNote)
        .where(*filters)
        .order_by(DebitNote.note_date.desc(), DebitNote.id.desc())
        .limit(limit)
        .offset(offset)
    ).scalars()
    return list(rows), total


def debit_summary(db: Session, note: DebitNote) -> DebitNoteSummary:
    loc = db.get(Location, note.location_id)
    supplier = db.get(Party, note.party_id)
    purchase = db.get(Purchase, note.purchase_id)
    return DebitNoteSummary(
        id=note.id,
        number=note.number,
        note_date=note.note_date,
        party_id=note.party_id,
        party_name=supplier.name if supplier else "",
        location_id=note.location_id,
        location_code=loc.code if loc else "",
        reason=note.reason,
        grand_total=note.grand_total,
        purchase_id=note.purchase_id,
        purchase_number=purchase.number if purchase else "",
        supplier_bill_no=purchase.bill_no if purchase else "",
    )


def debit_view(db: Session, note: DebitNote) -> DebitNoteOut:
    return DebitNoteOut(
        **debit_summary(db, note).model_dump(),
        financial_year=note.financial_year,
        supply_kind=note.supply_kind,
        taxable_value=note.taxable_value,
        cgst=note.cgst,
        sgst=note.sgst,
        igst=note.igst,
        round_off=note.round_off,
        lines=[DebitNoteLineOut.model_validate(x) for x in note.lines],
    )
