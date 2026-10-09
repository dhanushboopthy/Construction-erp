"""Sales invoices (Milestone 6): price, tax, save, and move stock and balance in one transaction.

Rules: B3 (price from rates, staff never type one), B4 (no cost for staff), B5 (below cost needs
the owner), B9 (one site per invoice), B10 (fulfilment source), B13 (no negative stock), B16
(gapless numbers, never edited), G3 (rounding), G5 (place of supply), G10 (discounts), G19
(idempotency)."""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import today_ist
from app.core.errors import (
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)
from app.core.tenancy import TENANT_ID
from app.domain import credit as credit_rules
from app.domain import dropship, gst, pricing
from app.domain import ledger as ledger_rules
from app.domain import weight_check as wc
from app.domain.fiscal import fy_label
from app.domain.ledger import Account, LedgerEntry
from app.domain.money import ZERO, money
from app.domain.stock_valuation import NegativeStockError, ensure_available
from app.domain.units import to_base
from app.models.enums import (
    ApprovalAction,
    AuditAction,
    DocType,
    FulfilmentSource,
    InvoiceStatus,
    LedgerAccount,
    PartyRef,
    PartyType,
    PaymentMode,
    StockRef,
    SupplyType,
)
from app.models.ledgers import PartyLedger
from app.models.masters import Item, Party, Site
from app.models.purchasing import Purchase, PurchaseLine
from app.models.sales import SalesInvoice, SalesLine
from app.models.setup import Location, ShopSettings
from app.schemas.sales import (
    InvoiceCreate,
    InvoiceLineIn,
    InvoiceLineOut,
    InvoiceLineOwnerOut,
    InvoiceOut,
    InvoiceOwnerOut,
    InvoicePreview,
    InvoiceSummary,
    PreviewLineOut,
)
from app.services import approvals as approval_service
from app.services import credit as credit_service
from app.services import items as item_service
from app.services import ledgers
from app.services import payments as payment_service
from app.services import rates as rate_service
from app.services import returns as returns_service
from app.services import transport as transport_service
from app.services.audit import record_event
from app.services.numbering import allocate_number
from app.services.shop_settings import get_settings_row

# Which owner approval clears which problem (G18).
APPROVAL_FOR = {
    "DISCOUNT_NEEDS_OWNER": ApprovalAction.DISCOUNT,
    "BELOW_COST": ApprovalAction.BELOW_COST,
    "BACKDATE_NEEDS_OWNER": ApprovalAction.BACKDATE,
    "CREDIT_NOT_ALLOWED": ApprovalAction.CREDIT_OVERRIDE,
    "CREDIT_LIMIT_EXCEEDED": ApprovalAction.CREDIT_OVERRIDE,
    "OVERDUE_INVOICES": ApprovalAction.CREDIT_OVERRIDE,
}


@dataclass
class Problem:
    line: int | None
    code: str
    message: str
    approval: bool = False
    field: str | None = None


@dataclass
class PricedLine:
    data: InvoiceLineIn
    item: Item
    unit: str
    base_qty: Decimal
    rate: Decimal | None = None
    source: pricing.RateSource | None = None
    discount: Decimal = ZERO
    tax: gst.LineTax | None = None
    source_location_id: int | None = None
    available: Decimal | None = None
    stock_after: Decimal | None = None
    cost: Decimal = ZERO
    weight: wc.WeightCheck | None = None
    problems: list[Problem] = field(default_factory=list)


@dataclass
class PricedInvoice:
    location: Location
    party: Party
    site: Site | None
    settings: ShopSettings
    invoice_date: date
    place_of_supply: str
    kind: gst.SupplyKind
    supply_type: SupplyType
    pending: Decimal
    lines: list[PricedLine]
    totals: gst.InvoiceTotals
    problems: list[Problem]
    paid: Decimal = ZERO
    overrides: list[str] = field(default_factory=list)  # credit rules the owner waived


def _balance(db: Session, party_id: int) -> Decimal:
    rows = db.execute(
        select(PartyLedger)
        .where(
            PartyLedger.tenant_id == TENANT_ID,
            PartyLedger.party_id == party_id,
            PartyLedger.account == LedgerAccount.RECEIVABLE,
        )
        .order_by(PartyLedger.entry_date, PartyLedger.id)
    ).scalars()
    entries = [
        LedgerEntry(r.entry_date, r.debit, r.credit, r.doc_no or "", r.applies_to) for r in rows
    ]
    return ledger_rules.balance(entries, Account.RECEIVABLE)


def price_invoice(
    db: Session,
    data: InvoiceCreate,
    *,
    is_owner: bool,
    can_access: bool,
    approved: frozenset[ApprovalAction] = frozenset(),
) -> PricedInvoice:
    """Work out every figure on the bill. Hard errors raise; fixable ones are collected in
    `problems` so the screen can show them while the bill is being keyed."""
    if not can_access:
        raise PermissionDeniedError("You can only bill from your own shop")
    settings = get_settings_row(db)
    location = db.get(Location, data.location_id)
    if location is None or location.tenant_id != TENANT_ID or not location.is_active:
        raise NotFoundError("Location not found or inactive", field="location_id")
    party = db.get(Party, data.party_id)
    if party is None or party.tenant_id != TENANT_ID or not party.is_active:
        raise NotFoundError("Customer not found or inactive", field="party_id")
    if party.type is PartyType.SUPPLIER:
        raise BusinessRuleError(
            "This is a supplier, not a customer", code="WRONG_PARTY_TYPE", field="party_id"
        )
    site: Site | None = None
    if data.site_id is not None:
        site = db.get(Site, data.site_id)
        if site is None or site.party_id != party.id or not site.is_active:
            raise BusinessRuleError(
                "That site does not belong to this customer", code="SITE_MISMATCH", field="site_id"
            )

    today = today_ist()
    on = data.invoice_date or today
    if on > today:
        raise BusinessRuleError(
            "A bill cannot be dated in the future", code="FUTURE_DATE", field="invoice_date"
        )
    # What the owner's PIN can clear: the same rights the owner has, for this one bill (G18).
    may_discount = is_owner or ApprovalAction.DISCOUNT in approved
    may_sell_below_cost = is_owner or ApprovalAction.BELOW_COST in approved
    problems: list[Problem] = []
    if on != today and not (is_owner or ApprovalAction.BACKDATE in approved):
        problems.append(
            Problem(
                None,
                "BACKDATE_NEEDS_OWNER",
                "Only the owner can back-date a bill.",
                True,
                "invoice_date",
            )
        )

    place = gst.place_of_supply(location.state_code, site.state_code if site else None)
    kind = gst.supply_kind(settings.state_code, place)
    supply_type = SupplyType.B2B if party.gstin else SupplyType.B2C

    used: dict[tuple[int, int], Decimal] = {}
    direct_used: dict[int, Decimal] = {}
    priced: list[PricedLine] = []
    for index, line in enumerate(data.lines):
        item = db.get(Item, line.item_id)
        if item is None or item.tenant_id != TENANT_ID or not item.is_active:
            raise NotFoundError("Item not found or inactive", field="item_id")
        unit = (line.unit or item.base_unit).lower()
        conversion = item_service.conversions(item).get(unit)
        if conversion is None:
            raise BusinessRuleError(
                f"{item.name} has no unit called {unit!r}", code="UNKNOWN_UNIT", field="unit"
            )
        try:
            base_qty = to_base(line.quantity, conversion)
        except ValueError as exc:
            raise BusinessRuleError(str(exc), code="UNIT_NOT_WHOLE", field="quantity") from exc
        row = PricedLine(line, item, unit, base_qty)
        priced.append(row)
        if line.slip_weight is not None:
            row.weight = wc.check_weight(base_qty, line.slip_weight, settings.weight_variance_pct)
            if row.weight.flagged and not (line.weight_note or "").strip():
                row.problems.append(
                    Problem(
                        index,
                        "WEIGHT_NOTE_REQUIRED",
                        f"The slip weight differs from the bill by {row.weight.variance_pct}%. "
                        "Write a note about why.",
                        False,
                        "weight_note",
                    )
                )

        # Price (B3): staff never choose it. Only the owner may override or discount.
        if (line.discount or line.rate_override is not None) and not may_discount:
            row.problems.append(
                Problem(
                    index,
                    "DISCOUNT_NEEDS_OWNER",
                    "A discount or a different price needs the owner.",
                    True,
                )
            )
        try:
            resolved = rate_service.resolve(db, item.id, party.id, on)
            row.rate, row.source = resolved.rate, resolved.source
        except BusinessRuleError as exc:
            row.problems.append(Problem(index, exc.code, exc.message, False, "item_id"))
        if line.rate_override is not None and may_discount:
            _, factor = conversion.unit, conversion.factor_to_base
            exclusive = pricing.exclusive_rate(
                line.rate_override, item.gst_rate, includes_gst=settings.rates_include_gst
            )
            row.rate = pricing.rate_per_base_unit(exclusive, factor)
            row.source = pricing.RateSource.MARKET
            row.problems = [p for p in row.problems if p.code != "PRICE_NOT_SET"]
        if line.discount and may_discount:
            if not line.discount_reason:
                row.problems.append(
                    Problem(
                        index,
                        "DISCOUNT_REASON",
                        "Give a reason for the discount.",
                        False,
                        "discount_reason",
                    )
                )
            row.discount = money(line.discount)

        # Stock (B13, B10): shop or godown stock must cover the quantity; direct lines move none.
        position, _ = ledgers.stock_position(db, item.id)
        row.cost = position.avg_cost if position.quantity > ZERO else ZERO
        if line.purchase_line_id is not None and line.source is not FulfilmentSource.DIRECT:
            row.problems.append(
                Problem(
                    index,
                    "LINK_NEEDS_DIRECT",
                    "Only a line sent direct from the supplier can name a purchase.",
                    False,
                    "purchase_line_id",
                )
            )
        if line.source is FulfilmentSource.DIRECT:
            row.source_location_id = None
            if line.purchase_line_id is not None:
                taken = direct_used.get(line.purchase_line_id, ZERO)
                try:
                    supplier_line = transport_service.check_linkable(
                        db, line.purchase_line_id, item.id, base_qty, also_taken=taken
                    )
                    row.cost = supplier_line.unit_cost  # the sale is costed at its own purchase
                    direct_used[line.purchase_line_id] = taken + base_qty
                except (BusinessRuleError, NotFoundError) as exc:
                    row.problems.append(
                        Problem(
                            index, "DIRECT_LINK_INVALID", exc.message, False, "purchase_line_id"
                        )
                    )
        else:
            where = (
                location.id
                if line.source is FulfilmentSource.SHOP
                else (line.source_location_id or location.id)
            )
            if line.source is FulfilmentSource.GODOWN and where == location.id:
                row.problems.append(
                    Problem(
                        index,
                        "GODOWN_NEEDS_PLACE",
                        "Pick the godown the stock comes from.",
                        False,
                        "source_location_id",
                    )
                )
            place_row = db.get(Location, where)
            if place_row is None or place_row.tenant_id != TENANT_ID or not place_row.is_active:
                raise NotFoundError("Stock location not found", field="source_location_id")
            row.source_location_id = where
            _, here = ledgers.stock_position(db, item.id, where)
            already = used.get((item.id, where), ZERO)
            row.available = here - already
            try:
                ensure_available(row.available, base_qty)
            except NegativeStockError:
                row.problems.append(
                    Problem(
                        index,
                        "INSUFFICIENT_STOCK",
                        f"Only {row.available.normalize():f} {item.base_unit} of "
                        f"{item.name} at {place_row.code}.",
                        False,
                        "quantity",
                    )
                )
            used[(item.id, where)] = already + base_qty
            row.stock_after = row.available - base_qty

        if row.rate is not None:
            try:
                taxable = gst.taxable_value(base_qty, row.rate, row.discount)
            except ValueError:
                row.problems.append(
                    Problem(
                        index,
                        "DISCOUNT_TOO_BIG",
                        "The discount is more than the line.",
                        False,
                        "discount",
                    )
                )
                taxable = ZERO
            row.tax = gst.line_tax(taxable, item.gst_rate, kind)
            # Selling below the average cost needs the owner (B5). The message gives no figures.
            if (
                base_qty > ZERO
                and row.cost > ZERO
                and taxable / base_qty < row.cost
                and not may_sell_below_cost
            ):
                row.problems.append(
                    Problem(index, "BELOW_COST", "This price needs the owner to approve it.", True)
                )

    totals = gst.invoice_totals([row.tax for row in priced if row.tax is not None])

    # Money taken now, the cash limit (G14) and the credit check on what stays unpaid (B8).
    paid = money(sum((x.amount for x in data.payments), ZERO))
    overrides: list[str] = []
    if paid > totals.grand_total:
        problems.append(
            Problem(
                None, "OVERPAID", "More money was entered than the bill total.", False, "payments"
            )
        )
    cash = money(sum((x.amount for x in data.payments if x.mode is PaymentMode.CASH), ZERO))
    if cash > ZERO:
        message = payment_service.check_cash_limit(db, party.id, on, cash)
        if message:
            problems.append(Problem(None, "CASH_LIMIT_REACHED", message, False, "payments"))
    unpaid = totals.grand_total - paid
    if unpaid > ZERO and totals.grand_total > ZERO:
        decision = credit_service.decide(db, party, settings, unpaid, on)
        messages = {
            credit_rules.CreditViolation.CREDIT_NOT_ALLOWED: (
                "This customer is not approved for credit. Take payment, or ask the owner."
            ),
            credit_rules.CreditViolation.CREDIT_LIMIT_EXCEEDED: (
                f"This would take the customer past their credit limit "
                f"(they owe ₹{decision.outstanding:,.2f}, ₹{decision.available:,.2f} is left)."
            ),
            credit_rules.CreditViolation.OVERDUE_INVOICES: (
                "This customer has overdue bills: " + ", ".join(decision.overdue) + "."
            ),
        }
        for violation in decision.violations:
            if is_owner or ApprovalAction.CREDIT_OVERRIDE in approved:
                overrides.append(violation.value)
            else:
                problems.append(
                    Problem(None, violation.value, messages[violation], True, "payments")
                )

    all_problems = problems + [p for row in priced for p in row.problems]
    return PricedInvoice(
        location=location,
        party=party,
        site=site,
        settings=settings,
        invoice_date=on,
        place_of_supply=place,
        kind=kind,
        supply_type=supply_type,
        pending=_balance(db, party.id),
        lines=priced,
        totals=totals,
        problems=all_problems,
        paid=paid,
        overrides=overrides,
    )


def preview(
    db: Session, data: InvoiceCreate, *, is_owner: bool, can_access: bool, actor_id: int
) -> InvoicePreview:
    approvals = approval_service.load_valid(db, data.approval_ids, actor_id, data.party_id)
    p = price_invoice(
        db,
        data,
        is_owner=is_owner,
        can_access=can_access,
        approved=frozenset(a.action for a in approvals),
    )
    lines = [
        PreviewLineOut(
            item_id=r.item.id,
            description=r.item.name,
            unit=r.unit,
            quantity=r.data.quantity,
            base_qty=r.base_qty,
            base_unit=r.item.base_unit,
            rate=r.rate,
            rate_source=r.source,
            discount=r.discount,
            taxable=r.tax.taxable if r.tax else ZERO,
            gst_rate=r.item.gst_rate,
            tax=r.tax.tax if r.tax else ZERO,
            line_total=r.tax.total if r.tax else ZERO,
            fulfilment_source=r.data.source,
            stock_available=r.available,
            stock_after=r.stock_after,
            weight_variance_pct=r.weight.variance_pct if r.weight else None,
            weight_flagged=r.weight.flagged if r.weight else False,
            problems=[x.message for x in r.problems],
        )
        for r in p.lines
    ]
    t = p.totals
    return InvoicePreview(
        place_of_supply=p.place_of_supply,
        supply_kind=p.kind,
        supply_type=p.supply_type,
        pending_balance=p.pending,
        taxable_value=t.taxable,
        cgst=t.cgst,
        sgst=t.sgst,
        igst=t.igst,
        round_off=t.round_off,
        grand_total=t.grand_total,
        paid_now=p.paid,
        balance_due=t.grand_total - p.paid,
        invoice_problems=[x.message for x in p.problems if x.line is None],
        needs_owner=any(x.approval for x in p.problems),
        approvals_needed=sorted({APPROVAL_FOR[x.code] for x in p.problems if x.approval}),
        lines=lines,
        can_save=not p.problems,
    )


def _existing(db: Session, key: str) -> SalesInvoice | None:
    return db.execute(
        select(SalesInvoice).where(
            SalesInvoice.tenant_id == TENANT_ID, SalesInvoice.idempotency_key == key
        )
    ).scalar_one_or_none()


def create(
    db: Session,
    data: InvoiceCreate,
    *,
    actor_id: int,
    is_owner: bool,
    can_access: bool,
    idempotency_key: str | None,
) -> tuple[SalesInvoice, bool]:
    """Save the bill. Returns (invoice, created); a repeated key returns the first invoice (G19)."""
    if idempotency_key:
        found = _existing(db, idempotency_key)
        if found:
            if found.party_id != data.party_id or found.location_id != data.location_id:
                raise ConflictError(
                    "This Idempotency-Key was used for a different bill",
                    code="IDEMPOTENCY_CONFLICT",
                )
            return found, False

    ledgers.lock_items(db, {line.item_id for line in data.lines})
    ledgers.lock_party(
        db, data.party_id
    )  # two counters cannot both spend the last of a credit limit
    approvals = approval_service.load_valid(db, data.approval_ids, actor_id, data.party_id)
    p = price_invoice(
        db,
        data,
        is_owner=is_owner,
        can_access=can_access,
        approved=frozenset(a.action for a in approvals),
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
        doc_type=DocType.SALES_INVOICE,
        on=p.invoice_date,
        fy_start_month=p.settings.financial_year_start_month,
    )
    credit_days = (
        p.party.credit_days if p.party.credit_days is not None else p.settings.default_credit_days
    )
    due = p.invoice_date + timedelta(days=credit_days) if p.party.credit_allowed else p.invoice_date
    t = p.totals
    invoice = SalesInvoice(
        tenant_id=TENANT_ID,
        number=number,
        financial_year=fy_label(p.invoice_date, p.settings.financial_year_start_month),
        location_id=p.location.id,
        party_id=p.party.id,
        site_id=p.site.id if p.site else None,
        bill_to_name=p.party.name,
        bill_to_address=p.party.address,
        bill_to_gstin=p.party.gstin,
        ship_to_name=p.site.name if p.site else None,
        ship_to_address=p.site.address if p.site else None,
        ship_to_gstin=p.site.gstin if p.site else None,
        place_of_supply=p.place_of_supply,
        supply_kind=p.kind,
        supply_type=p.supply_type,
        invoice_date=p.invoice_date,
        due_date=due,
        taxable_value=t.taxable,
        cgst=t.cgst,
        sgst=t.sgst,
        igst=t.igst,
        round_off=t.round_off,
        grand_total=t.grand_total,
        pending_balance_at_billing=p.pending,
        paid_at_billing=p.paid,
        vehicle_no=data.vehicle_no,
        remark=data.remark,
        idempotency_key=idempotency_key,
        status=InvoiceStatus.POSTED,
        lines=[
            SalesLine(
                tenant_id=TENANT_ID,
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
                discount=r.discount,
                discount_reason=r.data.discount_reason if r.discount else None,
                taxable=r.tax.taxable if r.tax else ZERO,
                gst_rate=r.item.gst_rate,
                cgst=r.tax.cgst if r.tax else ZERO,
                sgst=r.tax.sgst if r.tax else ZERO,
                igst=r.tax.igst if r.tax else ZERO,
                line_total=r.tax.total if r.tax else ZERO,
                fulfilment_source=r.data.source,
                source_location_id=r.source_location_id,
                stock_after=r.stock_after,
                cost_per_unit=r.cost,
                slip_weight=r.data.slip_weight,
                weight_variance_pct=r.weight.variance_pct if r.weight else ZERO,
                weight_flagged=r.weight.flagged if r.weight else False,
                weight_note=(r.data.weight_note or "").strip() or None if r.weight else None,
            )
            for i, r in enumerate(p.lines, start=1)
        ],
    )
    db.add(invoice)
    db.flush()
    for line, priced_line in zip(invoice.lines, p.lines, strict=True):
        if priced_line.data.purchase_line_id is not None:
            supplier_line = db.get(PurchaseLine, priced_line.data.purchase_line_id)
            if supplier_line is not None:
                transport_service.add_link(db, line, supplier_line, actor_id)
        if line.source_location_id is not None:
            ledgers.add_stock_move(
                db,
                item_id=line.item_id,
                location_id=line.source_location_id,
                entry_date=p.invoice_date,
                qty_out=line.base_qty,
                unit_cost=line.cost_per_unit,
                ref_type=StockRef.SALE,
                ref_id=invoice.id,
                narration=f"Invoice {number}",
                actor_id=actor_id,
            )
    ledgers.add_party_entry(
        db,
        party_id=p.party.id,
        site_id=p.site.id if p.site else None,
        account=LedgerAccount.RECEIVABLE,
        entry_date=p.invoice_date,
        ref_type=PartyRef.SALE,
        ref_id=invoice.id,
        doc_no=number,
        debit=t.grand_total,
        narration=f"Invoice {number}",
        actor_id=actor_id,
    )
    if data.payments:
        payment_service.receive_at_billing(
            db,
            party=p.party,
            site_id=p.site.id if p.site else None,
            location_id=p.location.id,
            invoice_number=number,
            on=p.invoice_date,
            parts=[(x.mode, x.amount, x.reference) for x in data.payments],
            actor_id=actor_id,
        )
    approval_service.mark_used(approvals, number)
    if p.overrides:
        # The owner waived a credit rule: leave a trail of who, which rule and for which bill.
        record_event(
            db,
            AuditAction.OVERRIDE,
            "sales_invoice",
            invoice.id,
            {"waived": p.overrides, "number": number, "party_id": p.party.id},
            user_id=actor_id,
        )
    db.commit()
    return invoice, True


# ---------------------------------------------------------------------------- reading


def get_invoice(db: Session, invoice_id: int) -> SalesInvoice:
    row = db.get(SalesInvoice, invoice_id)
    if row is None or row.tenant_id != TENANT_ID:
        raise NotFoundError("Invoice not found")
    return row


def list_invoices(
    db: Session,
    *,
    location_ids: frozenset[int] | None,
    party_id: int | None,
    q: str | None,
    date_from: date | None,
    date_to: date | None,
    limit: int,
    offset: int,
) -> tuple[list[SalesInvoice], int]:
    filters = [SalesInvoice.tenant_id == TENANT_ID]
    if location_ids is not None:
        filters.append(SalesInvoice.location_id.in_(location_ids))
    if party_id is not None:
        filters.append(SalesInvoice.party_id == party_id)
    if q:
        filters.append(
            SalesInvoice.number.ilike(f"%{q.strip()}%")
            | SalesInvoice.bill_to_name.ilike(f"%{q.strip()}%")
        )
    if date_from:
        filters.append(SalesInvoice.invoice_date >= date_from)
    if date_to:
        filters.append(SalesInvoice.invoice_date <= date_to)
    total = db.execute(select(func.count()).select_from(SalesInvoice).where(*filters)).scalar_one()
    rows = db.execute(
        select(SalesInvoice)
        .where(*filters)
        .order_by(SalesInvoice.invoice_date.desc(), SalesInvoice.id.desc())
        .limit(limit)
        .offset(offset)
    ).scalars()
    return list(rows), total


def summary(db: Session, inv: SalesInvoice) -> InvoiceSummary:
    loc = db.get(Location, inv.location_id)
    return InvoiceSummary(
        id=inv.id,
        number=inv.number,
        invoice_date=inv.invoice_date,
        party_id=inv.party_id,
        party_name=inv.bill_to_name,
        location_id=inv.location_id,
        location_code=loc.code if loc else "",
        supply_type=inv.supply_type,
        grand_total=inv.grand_total,
        status=inv.status,
    )


def invoice_view(db: Session, inv: SalesInvoice, with_cost: bool) -> InvoiceOut | InvoiceOwnerOut:
    base = summary(db, inv).model_dump() | {
        "financial_year": inv.financial_year,
        "site_id": inv.site_id,
        "bill_to_name": inv.bill_to_name,
        "bill_to_address": inv.bill_to_address,
        "bill_to_gstin": inv.bill_to_gstin,
        "ship_to_name": inv.ship_to_name,
        "ship_to_address": inv.ship_to_address,
        "ship_to_gstin": inv.ship_to_gstin,
        "place_of_supply": inv.place_of_supply,
        "supply_kind": inv.supply_kind,
        "due_date": inv.due_date,
        "taxable_value": inv.taxable_value,
        "cgst": inv.cgst,
        "sgst": inv.sgst,
        "igst": inv.igst,
        "round_off": inv.round_off,
        "pending_balance_at_billing": inv.pending_balance_at_billing,
        "paid_at_billing": inv.paid_at_billing,
        "vehicle_no": inv.vehicle_no,
        "remark": inv.remark,
    }
    returned = returns_service.returned_on_invoice(db, inv.id)

    def line_out(x: SalesLine) -> InvoiceLineOut:
        return InvoiceLineOut.model_validate(x).model_copy(
            update={"returned_qty": returned.get(x.id, ZERO)}
        )

    if not with_cost:
        return InvoiceOut(**base, lines=[line_out(x) for x in inv.lines])
    lines = []
    for x in inv.lines:
        link = transport_service.link_for(db, x.id)
        cost = link.unit_cost if link else x.cost_per_unit
        supplier_line = db.get(PurchaseLine, link.purchase_line_id) if link else None
        purchase = db.get(Purchase, supplier_line.purchase_id) if supplier_line else None
        lines.append(
            InvoiceLineOwnerOut(
                **line_out(x).model_dump(),
                cost_per_unit=cost,
                profit=dropship.profit(x.taxable, x.base_qty, cost),
                drop_ship_purchase=purchase.number if purchase else None,
            )
        )
    freight = transport_service.invoice_freight(db, inv.id)
    profit = money(sum((x.profit for x in lines), ZERO) - freight)
    return InvoiceOwnerOut(**base, lines=lines, profit=profit, freight=freight)
