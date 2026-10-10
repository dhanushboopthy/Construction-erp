"""Purchase orders, goods received and the three-way match (FM10, docs/FINANCE_REVIEW.md F25).

An order records what was asked of a supplier and at what rate; a goods receipt records what
arrived (it moves no stock: stock enters with the supplier's bill). A bill entered against an
order is checked against both. Beyond the quantity and rate tolerances (shop settings) a counter
user needs the owner's PIN (`po_mismatch` approval); the owner may go on. Every bill that is
linked to an order shows in the match report, which is worked out when it is read."""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import today_ist
from app.core.errors import BusinessRuleError, NotFoundError
from app.core.tenancy import TENANT_ID
from app.domain import orders as rules
from app.domain.money import ZERO, money, qty
from app.domain.units import to_base
from app.models.approvals import Approval
from app.models.enums import ApprovalAction, DocType, PartyType, Role
from app.models.masters import Item, Party
from app.models.orders import GoodsReceipt, GoodsReceiptLine, PurchaseOrder, PurchaseOrderLine
from app.models.purchasing import Purchase, PurchaseLine
from app.models.setup import AppUser, Location, ShopSettings
from app.schemas.orders import (
    BillRef,
    MatchReport,
    OrderCreate,
    OrderLineOut,
    OrderLineOwnerOut,
    OrderMatchRow,
    OrderOut,
    OrderOwnerOut,
    ReceiptCreate,
    ReceiptLineOut,
    ReceiptOut,
)
from app.services import approvals as approval_service
from app.services import closing as closing_service
from app.services import items as item_service
from app.services.numbering import allocate_number
from app.services.shop_settings import get_settings_row

# ---------------------------------------------------------------------------- orders


def get_order_row(db: Session, order_id: int) -> PurchaseOrder:
    row = db.get(PurchaseOrder, order_id)
    if row is None or row.tenant_id != TENANT_ID:
        raise NotFoundError("Purchase order not found")
    return row


def _place_and_supplier(db: Session, supplier_id: int, location_id: int) -> tuple[Party, Location]:
    supplier = db.get(Party, supplier_id)
    if supplier is None or supplier.tenant_id != TENANT_ID or not supplier.is_active:
        raise NotFoundError("Supplier not found or inactive", field="supplier_id")
    if supplier.type is PartyType.CUSTOMER:
        raise BusinessRuleError(
            "This party is a customer, not a supplier", code="WRONG_PARTY_TYPE", field="supplier_id"
        )
    place = db.get(Location, location_id)
    if place is None or place.tenant_id != TENANT_ID or not place.is_active:
        raise NotFoundError("Location not found or inactive", field="location_id")
    return supplier, place


def create_order(db: Session, data: OrderCreate, *, actor_id: int) -> PurchaseOrder:
    supplier, place = _place_and_supplier(db, data.supplier_id, data.location_id)
    today = today_ist()
    on = data.order_date or today
    if on > today:
        raise BusinessRuleError("An order cannot be dated in the future", code="FUTURE_DATE")
    if data.expected_date and data.expected_date < on:
        raise BusinessRuleError(
            "The expected date is before the order date", code="BAD_DATES", field="expected_date"
        )
    closing_service.ensure_day_open(db, place.id, on)
    settings = get_settings_row(db)
    lines: list[PurchaseOrderLine] = []
    for index, line in enumerate(data.lines, start=1):
        item = db.get(Item, line.item_id)
        if item is None or item.tenant_id != TENANT_ID or not item.is_active:
            raise NotFoundError("Item not found or inactive", field=f"lines[{index - 1}].item_id")
        conversion = item_service.conversions(item).get(line.unit.lower())
        if conversion is None:
            raise BusinessRuleError(
                f"{item.name} has no unit called {line.unit!r}",
                code="UNKNOWN_UNIT",
                field=f"lines[{index - 1}].unit",
            )
        try:
            base = to_base(line.quantity, conversion)
        except ValueError as exc:
            raise BusinessRuleError(
                str(exc), code="UNIT_NOT_WHOLE", field=f"lines[{index - 1}].quantity"
            ) from exc
        lines.append(
            PurchaseOrderLine(
                tenant_id=TENANT_ID,
                line_no=index,
                item_id=item.id,
                unit=line.unit.lower(),
                quantity=line.quantity,
                base_qty=base,
                rate=line.rate,
            )
        )
    number = allocate_number(
        db,
        location_id=place.id,
        doc_type=DocType.PURCHASE_ORDER,
        on=on,
        fy_start_month=settings.financial_year_start_month,
    )
    order = PurchaseOrder(
        tenant_id=TENANT_ID,
        number=number,
        supplier_id=supplier.id,
        location_id=place.id,
        order_date=on,
        expected_date=data.expected_date,
        note=data.note,
        created_by=actor_id,
        lines=lines,
    )
    db.add(order)
    db.commit()
    return order


def _received_by_line(db: Session, order_id: int) -> dict[int, Decimal]:
    rows = db.execute(
        select(GoodsReceiptLine.order_line_id, func.sum(GoodsReceiptLine.base_qty))
        .join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptLine.receipt_id)
        .where(GoodsReceipt.order_id == order_id)
        .group_by(GoodsReceiptLine.order_line_id)
    ).all()
    return dict(rows)


def _billed_by_item(
    db: Session, order_id: int, up_to_purchase_id: int | None = None
) -> dict[int, Decimal]:
    stmt = (
        select(PurchaseLine.item_id, func.sum(PurchaseLine.billed_qty))
        .join(Purchase, Purchase.id == PurchaseLine.purchase_id)
        .where(Purchase.purchase_order_id == order_id)
        .group_by(PurchaseLine.item_id)
    )
    if up_to_purchase_id is not None:
        stmt = stmt.where(Purchase.id <= up_to_purchase_id)
    return dict(db.execute(stmt).all())


def order_view(db: Session, order: PurchaseOrder, *, owner: bool) -> OrderOut | OrderOwnerOut:
    supplier = db.get(Party, order.supplier_id)
    place = db.get(Location, order.location_id)
    items = {i.id: i for i in db.scalars(select(Item).where(Item.tenant_id == TENANT_ID))}
    received = _received_by_line(db, order.id)
    billed = _billed_by_item(db, order.id)
    lines: list[OrderLineOut] = []
    owner_lines: list[OrderLineOwnerOut] = []
    for line in order.lines:
        item = items[line.item_id]
        common = {
            "id": line.id,
            "line_no": line.line_no,
            "item_id": line.item_id,
            "item_name": item.name,
            "unit": line.unit,
            "quantity": line.quantity,
            "base_qty": line.base_qty,
            "base_unit": item.base_unit,
            "received_qty": qty(received.get(line.id, ZERO)),
            "billed_qty": qty(billed.get(line.item_id, ZERO)),
        }
        lines.append(OrderLineOut(**common))
        owner_lines.append(
            OrderLineOwnerOut(**common, rate=line.rate, value=money(line.quantity * line.rate))
        )
    receipts = db.scalars(
        select(GoodsReceipt).where(GoodsReceipt.order_id == order.id).order_by(GoodsReceipt.id)
    ).all()
    by_line = {x.id: x for x in order.lines}
    receipt_out = [
        ReceiptOut(
            id=r.id,
            number=r.number,
            receipt_date=r.receipt_date,
            note=r.note,
            lines=[
                ReceiptLineOut(
                    order_line_id=x.order_line_id,
                    item_name=items[x.item_id].name,
                    unit=x.unit,
                    quantity=x.quantity,
                    base_qty=x.base_qty,
                )
                for x in r.lines
            ],
        )
        for r in receipts
    ]
    bills = db.scalars(
        select(Purchase).where(Purchase.purchase_order_id == order.id).order_by(Purchase.id)
    ).all()
    all_received = all(received.get(x.id, ZERO) >= x.base_qty for x in order.lines)
    all_billed = all(billed.get(x.item_id, ZERO) >= x.base_qty for x in by_line.values())
    status = "billed" if all_billed else "received" if all_received else "open"
    base = {
        "id": order.id,
        "number": order.number,
        "supplier_id": order.supplier_id,
        "supplier_name": supplier.name if supplier else "",
        "location_id": order.location_id,
        "location_code": place.code if place else "",
        "order_date": order.order_date,
        "expected_date": order.expected_date,
        "note": order.note,
        "status": status,
        "receipts": receipt_out,
        "bills": [
            BillRef(id=b.id, number=b.number, bill_no=b.bill_no, bill_date=b.bill_date)
            for b in bills
        ],
    }
    if owner:
        return OrderOwnerOut(
            **base,
            lines=owner_lines,
            value=money(sum((x.value for x in owner_lines), ZERO)),
        )
    return OrderOut(**base, lines=lines)


def list_orders(
    db: Session,
    *,
    owner: bool,
    location_ids: frozenset[int] | None,
    supplier_id: int | None,
    open_only: bool,
) -> list[OrderOut | OrderOwnerOut]:
    stmt = select(PurchaseOrder).where(PurchaseOrder.tenant_id == TENANT_ID)
    if location_ids is not None:
        stmt = stmt.where(PurchaseOrder.location_id.in_(location_ids))
    if supplier_id is not None:
        stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)
    views = [
        order_view(db, o, owner=owner)
        for o in db.scalars(stmt.order_by(PurchaseOrder.id.desc()).limit(200))
    ]
    return [v for v in views if v.status != "billed"] if open_only else views


def get_order(
    db: Session, order_id: int, *, owner: bool, can_access: Callable[[int], bool]
) -> OrderOut | OrderOwnerOut:
    order = get_order_row(db, order_id)
    if not can_access(order.location_id):
        raise NotFoundError("Purchase order not found")
    return order_view(db, order, owner=owner)


# ---------------------------------------------------------------------------- goods received


def create_receipt(
    db: Session,
    order_id: int,
    data: ReceiptCreate,
    *,
    actor_id: int,
    is_owner: bool,
    can_access: Callable[[int], bool],
) -> GoodsReceipt:
    order = get_order_row(db, order_id)
    if not can_access(order.location_id):
        raise NotFoundError("Purchase order not found")
    today = today_ist()
    on = data.receipt_date or today
    if on > today:
        raise BusinessRuleError("A receipt cannot be dated in the future", code="FUTURE_DATE")
    if on != today and not is_owner:
        raise BusinessRuleError(
            "Only the owner can enter a receipt for an earlier day.",
            code="BACKDATE_NEEDS_OWNER",
            field="receipt_date",
        )
    if on < order.order_date:
        raise BusinessRuleError(
            "Goods cannot arrive before the order was made", code="BAD_DATES", field="receipt_date"
        )
    closing_service.ensure_day_open(db, order.location_id, on)
    by_id = {x.id: x for x in order.lines}
    seen: set[int] = set()
    lines: list[GoodsReceiptLine] = []
    for index, asked in enumerate(data.lines):
        line = by_id.get(asked.order_line_id)
        if line is None:
            raise NotFoundError(
                "That line is not on this order", field=f"lines[{index}].order_line_id"
            )
        if line.id in seen:
            raise BusinessRuleError(
                "A line is listed twice. Combine the quantity into one row.",
                code="LINE_REPEATED",
                field="lines",
            )
        seen.add(line.id)
        item = db.get(Item, line.item_id)
        if item is None:
            raise NotFoundError("Item not found", field=f"lines[{index}].order_line_id")
        conversion = item_service.conversions(item)[line.unit]
        try:
            base = to_base(asked.quantity, conversion)
        except ValueError as exc:
            raise BusinessRuleError(
                str(exc), code="UNIT_NOT_WHOLE", field=f"lines[{index}].quantity"
            ) from exc
        lines.append(
            GoodsReceiptLine(
                tenant_id=TENANT_ID,
                order_line_id=line.id,
                item_id=line.item_id,
                unit=line.unit,
                quantity=asked.quantity,
                base_qty=base,
            )
        )
    settings = get_settings_row(db)
    number = allocate_number(
        db,
        location_id=order.location_id,
        doc_type=DocType.GOODS_RECEIPT,
        on=on,
        fy_start_month=settings.financial_year_start_month,
    )
    receipt = GoodsReceipt(
        tenant_id=TENANT_ID,
        number=number,
        order_id=order.id,
        location_id=order.location_id,
        receipt_date=on,
        note=data.note,
        created_by=actor_id,
        lines=lines,
    )
    db.add(receipt)
    db.commit()
    return receipt


# ---------------------------------------------------------------------------- the match


@dataclass(frozen=True)
class BillLine:
    """One item on a supplier bill, in base units and a rate per base unit."""

    item_id: int
    item_name: str
    billed_qty: Decimal
    rate: Decimal


def _per_item(lines: list[BillLine]) -> dict[int, BillLine]:
    """Merge lines of one item: quantities add, the rate is the value-weighted average."""
    total_qty: dict[int, Decimal] = defaultdict(lambda: ZERO)
    total_value: dict[int, Decimal] = defaultdict(lambda: ZERO)
    names: dict[int, str] = {}
    for x in lines:
        total_qty[x.item_id] += x.billed_qty
        total_value[x.item_id] += x.billed_qty * x.rate
        names[x.item_id] = x.item_name
    return {
        i: BillLine(i, names[i], q, total_value[i] / q if q else ZERO) for i, q in total_qty.items()
    }


@dataclass(frozen=True)
class _OrderFigures:
    ordered: dict[int, Decimal]
    received: dict[int, Decimal]
    rate: dict[int, Decimal]  # per base unit


def _figures(db: Session, order: PurchaseOrder) -> _OrderFigures:
    ordered: dict[int, Decimal] = defaultdict(lambda: ZERO)
    value: dict[int, Decimal] = defaultdict(lambda: ZERO)
    received: dict[int, Decimal] = defaultdict(lambda: ZERO)
    got = _received_by_line(db, order.id)
    for line in order.lines:
        ordered[line.item_id] += line.base_qty
        value[line.item_id] += line.quantity * line.rate
        received[line.item_id] += got.get(line.id, ZERO)
    return _OrderFigures(
        dict(ordered),
        dict(received),
        {i: value[i] / ordered[i] for i in ordered},
    )


def _match(
    figures: _OrderFigures, line: BillLine, billed_total: Decimal, settings: ShopSettings
) -> rules.LineMatch:
    return rules.match_line(
        ordered=figures.ordered.get(line.item_id, ZERO),
        received=figures.received.get(line.item_id, ZERO),
        billed=billed_total,
        this_billed=line.billed_qty,
        po_rate=figures.rate.get(line.item_id, ZERO),
        bill_rate=line.rate,
        qty_tolerance_pct=settings.po_qty_tolerance_pct,
        rate_tolerance_pct=settings.po_rate_tolerance_pct,
    )


def check_bill(
    db: Session,
    order_id: int,
    *,
    supplier_id: int,
    location_id: int,
    lines: list[BillLine],
    approval_ids: list[int],
    actor_id: int,
    is_owner: bool,
    settings: ShopSettings,
) -> tuple[PurchaseOrder, Approval | None]:
    """Three-way match of a bill about to be saved against its order and the goods received.

    Returns the order and the owner approval used, if any. A counter user whose bill is out of
    tolerance is refused (409 MATCH_EXCEPTION, owner approval needed); the owner may go on. The
    message never carries a rupee value."""
    order = get_order_row(db, order_id)
    if order.supplier_id != supplier_id:
        raise BusinessRuleError(
            "This order was placed with a different supplier",
            code="ORDER_SUPPLIER_MISMATCH",
            field="purchase_order_id",
        )
    if order.location_id != location_id:
        raise BusinessRuleError(
            "This order was placed for a different shop or godown",
            code="ORDER_PLACE_MISMATCH",
            field="purchase_order_id",
        )
    figures = _figures(db, order)
    already = _billed_by_item(db, order.id)
    merged = _per_item(lines)
    reasons: list[str] = []
    for item_id, line in merged.items():
        if item_id not in figures.ordered:
            reasons.append(f"{line.item_name}: not on the order.")
            continue
        m = _match(figures, line, already.get(item_id, ZERO) + line.billed_qty, settings)
        reasons += [f"{line.item_name}: {r}" for r in m.reasons]
    if not reasons:
        return order, None
    if is_owner:
        return order, None
    approvals = approval_service.load_valid(db, approval_ids, actor_id, party_id=0)
    match = next((a for a in approvals if a.action is ApprovalAction.PO_MISMATCH), None)
    if approval_ids and match is None:
        raise BusinessRuleError(
            "That approval is not for a bill that differs from its order. Ask the owner again.",
            code="APPROVAL_INVALID",
            requires_owner_approval=True,
        )
    if match is None:
        raise BusinessRuleError(
            "This bill does not match its order. " + " ".join(reasons),
            code="MATCH_EXCEPTION",
            field="purchase_order_id",
            requires_owner_approval=True,
        )
    return order, match


def match_report(
    db: Session, date_from: date, date_to: date, *, only_exceptions: bool
) -> MatchReport:
    """Every bill entered against an order in the dates, item by item, against the order and the
    goods received so far. PPV (purchase price variance) is on each row."""
    if date_to < date_from:
        raise BusinessRuleError(
            "The end date is before the start date", code="BAD_RANGE", field="date_to"
        )
    settings = get_settings_row(db)
    items = {i.id: i for i in db.scalars(select(Item).where(Item.tenant_id == TENANT_ID))}
    owners = {u.id for u in db.scalars(select(AppUser).where(AppUser.role == Role.OWNER))}
    purchases = db.scalars(
        select(Purchase)
        .where(
            Purchase.tenant_id == TENANT_ID,
            Purchase.purchase_order_id.is_not(None),
            Purchase.bill_date >= date_from,
            Purchase.bill_date <= date_to,
        )
        .order_by(Purchase.bill_date, Purchase.id)
    ).all()
    rows: list[OrderMatchRow] = []
    figures_cache: dict[int, _OrderFigures] = {}
    lines_checked = 0
    ppv_all = ZERO
    for purchase in purchases:
        order = get_order_row(db, int(purchase.purchase_order_id or 0))
        figures = figures_cache.setdefault(order.id, _figures(db, order))
        supplier = db.get(Party, purchase.supplier_id)
        up_to = _billed_by_item(db, order.id, purchase.id)
        bill_lines = [
            BillLine(
                x.item_id,
                items[x.item_id].name,
                x.billed_qty,
                (x.rate * x.quantity / x.billed_qty) if x.billed_qty else ZERO,
            )
            for x in purchase.lines
        ]
        for item_id, line in _per_item(bill_lines).items():
            lines_checked += 1
            m = _match(figures, line, up_to.get(item_id, ZERO), settings)
            ppv_all += m.ppv
            if only_exceptions and m.ok:
                continue
            rows.append(
                OrderMatchRow(
                    purchase_id=purchase.id,
                    purchase_number=purchase.number,
                    bill_no=purchase.bill_no,
                    bill_date=purchase.bill_date,
                    order_number=order.number,
                    supplier_name=supplier.name if supplier else "",
                    item_name=line.item_name,
                    base_unit=items[item_id].base_unit,
                    ordered_qty=qty(figures.ordered.get(item_id, ZERO)),
                    received_qty=qty(figures.received.get(item_id, ZERO)),
                    billed_qty=qty(up_to.get(item_id, ZERO)),
                    qty_over_received_pct=m.qty_over_received_pct,
                    order_rate=(
                        figures.rate[item_id].quantize(Decimal("0.0001"))
                        if item_id in figures.rate
                        else None
                    ),
                    bill_rate=line.rate.quantize(Decimal("0.0001")),
                    rate_variance_pct=m.rate_variance_pct,
                    ppv=m.ppv,
                    ok=m.ok,
                    reasons=m.reasons,
                    approved=purchase.match_approval_id is not None,
                    entered_by_owner=purchase.created_by in owners,
                )
            )
    return MatchReport(
        date_from=date_from,
        date_to=date_to,
        qty_tolerance_pct=settings.po_qty_tolerance_pct,
        rate_tolerance_pct=settings.po_rate_tolerance_pct,
        rows=rows,
        bills_checked=len(purchases),
        lines_checked=lines_checked,
        exceptions=sum(1 for r in rows if not r.ok),
        ppv_total=money(ppv_all),  # over every line checked, not only the ones listed
    )
