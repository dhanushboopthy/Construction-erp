"""Purchases with landed cost (Milestone 4, rules B1, B2, B6, B13, G1, G6).

One use case, one transaction: price every line with `domain.landed_cost`, take the next
purchase number, save the bill, add the stock (stock mode) and the supplier's payable."""

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import (
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)
from app.core.tenancy import TENANT_ID
from app.domain import landed_cost as lc
from app.domain import weight_check as wc
from app.domain.money import ZERO, money, qty
from app.domain.units import UnitConversion, to_base
from app.models.enums import (
    DocType,
    LedgerAccount,
    PartyRef,
    PartyType,
    PurchaseMode,
    PurchaseStatus,
    StockRef,
)
from app.models.masters import Item, Party
from app.models.purchasing import CostComponent, Purchase, PurchaseCost, PurchaseLine
from app.models.setup import Location
from app.schemas.purchases import (
    CostComponentIn,
    CostComponentUpdate,
    PreviewLine,
    PurchaseCostOut,
    PurchaseCreate,
    PurchaseLineIn,
    PurchaseLineOut,
    PurchaseLineOwnerOut,
    PurchaseOut,
    PurchaseOwnerOut,
    PurchasePreview,
)
from app.services import closing as closing_service
from app.services import items as item_service
from app.services import ledgers
from app.services.numbering import allocate_number
from app.services.shop_settings import get_settings_row

# ---------------------------------------------------------------------------- charge master


def list_components(db: Session, include_inactive: bool = False) -> list[CostComponent]:
    stmt = select(CostComponent).where(CostComponent.tenant_id == TENANT_ID)
    if not include_inactive:
        stmt = stmt.where(CostComponent.is_active.is_(True))
    return list(db.execute(stmt.order_by(CostComponent.name)).scalars())


def _component(db: Session, component_id: int) -> CostComponent:
    row = db.get(CostComponent, component_id)
    if row is None or row.tenant_id != TENANT_ID:
        raise NotFoundError("Charge type not found", field="component_id")
    return row


def create_component(db: Session, data: CostComponentIn) -> CostComponent:
    taken = db.execute(
        select(CostComponent.id).where(
            CostComponent.tenant_id == TENANT_ID,
            func.lower(CostComponent.name) == data.name.lower(),
        )
    ).first()
    if taken:
        raise ConflictError(
            "A charge type with this name exists", code="COMPONENT_EXISTS", field="name"
        )
    row = CostComponent(tenant_id=TENANT_ID, **data.model_dump())
    db.add(row)
    db.commit()
    return row


def update_component(db: Session, component_id: int, data: CostComponentUpdate) -> CostComponent:
    row = _component(db, component_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    db.commit()
    return row


# ---------------------------------------------------------------------------- pricing


@dataclass
class PricedCharge:
    component_id: int | None
    name: str
    basis: lc.ChargeBasis
    rate: Decimal
    total: Decimal
    on_supplier_bill: bool


@dataclass
class PricedLine:
    item: Item
    data: PurchaseLineIn
    gst_rate: Decimal
    billed_qty: Decimal
    received_qty: Decimal
    result: lc.LandedCost
    weight: wc.WeightCheck
    charges: list[PricedCharge] = field(default_factory=list)

    @property
    def on_bill_charges(self) -> Decimal:
        return money(sum((c.total for c in self.charges if c.on_supplier_bill), ZERO))


def _weight_tons(item: Item, base_qty: Decimal) -> Decimal:
    """Received weight in tons, needed only for per-ton charges."""
    if item.base_unit == "kg":
        return base_qty / 1000
    if item.weight_per_piece_kg:
        return base_qty * item.weight_per_piece_kg / 1000
    return ZERO


def _price_line(
    db: Session,
    line: PurchaseLineIn,
    include_gst_in_cost: bool,
    items: dict[int, Item],
    weight_threshold: Decimal,
) -> PricedLine:
    item = items.get(line.item_id)
    if item is None or not item.is_active:
        raise NotFoundError("Item not found or inactive", field="item_id")
    table = item_service.conversions(item)
    conversion: UnitConversion | None = table.get(line.unit.lower())
    if conversion is None:
        raise BusinessRuleError(
            f"{item.name} has no unit called {line.unit!r}. "
            f"Known units: {', '.join(sorted(table))}",
            code="UNKNOWN_UNIT",
            field="unit",
        )
    received_entered = (
        line.received_quantity if line.received_quantity is not None else line.quantity
    )
    try:
        billed_base = to_base(line.quantity, conversion)
        received_base = to_base(received_entered, conversion)
    except ValueError as exc:
        raise BusinessRuleError(str(exc), code="UNIT_NOT_WHOLE", field="quantity") from exc

    gst_rate = line.gst_rate if line.gst_rate is not None else item.gst_rate
    charges: list[PricedCharge] = []
    domain_charges: list[lc.Charge] = []
    for charge in line.charges:
        component = _component(db, charge.component_id) if charge.component_id else None
        name = charge.name or (component.name if component else "")
        basis = charge.basis or (component.basis if component else lc.ChargeBasis.FLAT)
        domain_charges.append(lc.Charge(name, basis, charge.amount))
        charges.append(
            PricedCharge(
                charge.component_id, name, basis, charge.amount, ZERO, charge.on_supplier_bill
            )
        )

    domain_line = lc.PurchaseLine(
        billed_qty=billed_base,
        received_qty=received_base,
        rate=line.rate / conversion.factor_to_base,
        gst_rate=gst_rate,
        received_weight_tons=_weight_tons(item, received_base),
        charges=domain_charges,
        line_value=money(line.quantity * line.rate),
    )
    try:
        result = lc.landed_cost(domain_line, include_gst_in_cost)
        for priced, domain_charge in zip(charges, domain_charges, strict=True):
            priced.total = lc.charge_amount(domain_charge, domain_line)
    except ValueError as exc:
        raise BusinessRuleError(
            f"{item.name}: {exc}. Use a charge per bag or per trip for items that are not weighed.",
            code="CHARGE_NEEDS_WEIGHT",
            field="charges",
        ) from exc
    weight = wc.check_weight(billed_base, received_base, weight_threshold)
    return PricedLine(item, line, gst_rate, billed_base, received_base, result, weight, charges)


def _load_context(db: Session, data: PurchaseCreate) -> tuple[Party, Location, dict[int, Item]]:
    supplier = db.get(Party, data.supplier_id)
    if supplier is None or supplier.tenant_id != TENANT_ID or not supplier.is_active:
        raise NotFoundError("Supplier not found or inactive", field="supplier_id")
    if supplier.type is PartyType.CUSTOMER:
        raise BusinessRuleError(
            "This party is a customer, not a supplier", code="WRONG_PARTY_TYPE", field="supplier_id"
        )
    location = db.get(Location, data.location_id)
    if location is None or location.tenant_id != TENANT_ID or not location.is_active:
        raise NotFoundError("Location not found or inactive", field="location_id")
    ids = {line.item_id for line in data.lines}
    items = {
        i.id: i
        for i in db.execute(select(Item).where(Item.id.in_(ids))).scalars()
        if i.tenant_id == TENANT_ID
    }
    return supplier, location, items


def price(db: Session, data: PurchaseCreate) -> tuple[list[PricedLine], bool]:
    settings = get_settings_row(db)
    _, _, items = _load_context(db, data)
    priced = [
        _price_line(db, line, settings.include_gst_in_cost, items, settings.weight_variance_pct)
        for line in data.lines
    ]
    return priced, settings.include_gst_in_cost


def _shortage_value(check: wc.WeightCheck, goods_value: Decimal, billed_qty: Decimal) -> Decimal:
    """What a short delivery is worth, at the price on the supplier's bill."""
    return check.shortage_value(goods_value / billed_qty)


def _cost_out(index: int, charge: PricedCharge) -> PurchaseCostOut:
    return PurchaseCostOut(
        id=index,
        component_id=charge.component_id,
        name=charge.name,
        basis=charge.basis,
        rate=charge.rate,
        total=charge.total,
        on_supplier_bill=charge.on_supplier_bill,
    )


def preview(db: Session, data: PurchaseCreate) -> PurchasePreview:
    """The numbers the owner sees while keying a bill. The server computes them, so the
    screen never does money maths of its own (ADR 0002)."""
    priced, gst_in_cost = price(db, data)
    lines = [
        PreviewLine(
            item_id=p.item.id,
            item_name=p.item.name,
            base_unit=p.item.base_unit,
            billed_qty=p.billed_qty,
            received_qty=p.received_qty,
            goods_value=p.result.goods_value,
            gst_amount=p.result.gst,
            charges_total=p.result.charges_total,
            total_cost=p.result.total_cost,
            unit_cost=p.result.unit_cost,
            weight_variance_pct=p.weight.variance_pct,
            weight_flagged=p.weight.flagged,
            shortage_value=_shortage_value(p.weight, p.result.goods_value, p.billed_qty),
            costs=[_cost_out(i, c) for i, c in enumerate(p.charges, start=1)],
        )
        for p in priced
    ]
    goods = money(sum((p.result.goods_value for p in priced), ZERO))
    gst = money(sum((p.result.gst for p in priced), ZERO))
    charges = money(sum((p.result.charges_total for p in priced), ZERO))
    payable = money(
        sum(
            (
                lc.supplier_payable(p.result.goods_value, p.result.gst, p.on_bill_charges)
                for p in priced
            ),
            ZERO,
        )
    )
    return PurchasePreview(
        goods_value=goods,
        gst_amount=gst,
        charges_total=charges,
        supplier_payable=payable,
        gst_in_cost=gst_in_cost,
        lines=lines,
    )


# ---------------------------------------------------------------------------- posting


def create(db: Session, data: PurchaseCreate, *, actor_id: int, can_access: bool) -> Purchase:
    if not can_access:
        raise PermissionDeniedError("You can only enter purchases for your own shop")
    supplier, location, items = _load_context(db, data)
    closing_service.ensure_day_open(db, location.id, data.bill_date)
    duplicate = db.execute(
        select(Purchase.number).where(
            Purchase.tenant_id == TENANT_ID,
            Purchase.supplier_id == supplier.id,
            func.lower(Purchase.bill_no) == data.bill_no.lower(),
        )
    ).first()
    if duplicate:
        raise ConflictError(
            f"This supplier's bill {data.bill_no} is already entered as {duplicate[0]}",
            code="DUPLICATE_BILL",
            field="bill_no",
        )
    settings = get_settings_row(db)
    priced = [
        _price_line(db, line, settings.include_gst_in_cost, items, settings.weight_variance_pct)
        for line in data.lines
    ]

    for index, p in enumerate(priced):
        if p.weight.flagged and not (p.data.weight_note or "").strip():
            raise BusinessRuleError(
                f"{p.item.name}: received weight differs from the bill by "
                f"{p.weight.variance_pct}%. Write a note about why.",
                code="WEIGHT_NOTE_REQUIRED",
                field=f"lines[{index}].weight_note",
            )

    number = allocate_number(
        db,
        location_id=location.id,
        doc_type=DocType.PURCHASE_ENTRY,
        on=data.bill_date,
        fy_start_month=settings.financial_year_start_month,
    )
    goods = money(sum((p.result.goods_value for p in priced), ZERO))
    gst = money(sum((p.result.gst for p in priced), ZERO))
    charges = money(sum((p.result.charges_total for p in priced), ZERO))
    payable = money(
        sum(
            (
                lc.supplier_payable(p.result.goods_value, p.result.gst, p.on_bill_charges)
                for p in priced
            ),
            ZERO,
        )
    )
    purchase = Purchase(
        tenant_id=TENANT_ID,
        number=number,
        supplier_id=supplier.id,
        location_id=location.id,
        bill_no=data.bill_no.strip(),
        bill_date=data.bill_date,
        due_date=data.due_date,
        mode=data.mode,
        status=PurchaseStatus.POSTED,
        goods_value=goods,
        gst_amount=gst,
        charges_total=charges,
        supplier_payable=payable,
        note=data.note,
        lines=[
            PurchaseLine(
                tenant_id=TENANT_ID,
                line_no=index,
                item_id=p.item.id,
                unit=p.data.unit.lower(),
                quantity=p.data.quantity,
                received_quantity=p.data.received_quantity or p.data.quantity,
                billed_qty=qty(p.billed_qty),
                received_qty=qty(p.received_qty),
                rate=p.data.rate,
                gst_rate=p.gst_rate,
                goods_value=p.result.goods_value,
                gst_amount=p.result.gst,
                charges_total=p.result.charges_total,
                total_cost=p.result.total_cost,
                unit_cost=p.result.unit_cost,
                weight_variance_pct=p.weight.variance_pct,
                weight_flagged=p.weight.flagged,
                weight_note=(p.data.weight_note or "").strip() or None,
                costs=[
                    PurchaseCost(
                        tenant_id=TENANT_ID,
                        component_id=c.component_id,
                        name=c.name,
                        basis=c.basis,
                        rate=c.rate,
                        total=c.total,
                        on_supplier_bill=c.on_supplier_bill,
                    )
                    for c in p.charges
                ],
            )
            for index, p in enumerate(priced, start=1)
        ],
    )
    db.add(purchase)
    db.flush()

    if data.mode is PurchaseMode.STOCK:
        for line in purchase.lines:
            ledgers.add_stock_move(
                db,
                item_id=line.item_id,
                location_id=location.id,
                entry_date=data.bill_date,
                qty_in=line.received_qty,
                unit_cost=line.unit_cost,
                ref_type=StockRef.PURCHASE,
                ref_id=purchase.id,
                narration=f"Purchase {number}",
                actor_id=actor_id,
            )
    ledgers.add_party_entry(
        db,
        party_id=supplier.id,
        site_id=None,
        account=LedgerAccount.PAYABLE,
        entry_date=data.bill_date,
        ref_type=PartyRef.PURCHASE,
        ref_id=purchase.id,
        doc_no=number,
        credit=payable,
        narration=f"Bill {purchase.bill_no}",
        actor_id=actor_id,
    )
    db.commit()
    return purchase


def get_purchase(db: Session, purchase_id: int) -> Purchase:
    row = db.get(Purchase, purchase_id)
    if row is None or row.tenant_id != TENANT_ID:
        raise NotFoundError("Purchase not found")
    return row


# ---------------------------------------------------------------------------- views


def purchase_view(
    db: Session, purchase: Purchase, with_cost: bool
) -> PurchaseOut | PurchaseOwnerOut:
    """Owner model with every money field, or staff model with quantities only (rule B4)."""
    supplier = db.get(Party, purchase.supplier_id)
    location = db.get(Location, purchase.location_id)
    items = {i.id: i for i in db.execute(select(Item)).scalars()}
    base = {
        "id": purchase.id,
        "number": purchase.number,
        "supplier_id": purchase.supplier_id,
        "supplier_name": supplier.name if supplier else "",
        "location_id": purchase.location_id,
        "location_code": location.code if location else "",
        "bill_no": purchase.bill_no,
        "bill_date": purchase.bill_date,
        "due_date": purchase.due_date,
        "mode": purchase.mode,
        "status": purchase.status,
        "note": purchase.note,
    }

    def line_base(line: PurchaseLine) -> dict[str, object]:
        item = items[line.item_id]
        return {
            "id": line.id,
            "line_no": line.line_no,
            "item_id": line.item_id,
            "item_name": item.name,
            "unit": line.unit,
            "quantity": line.quantity,
            "received_quantity": line.received_quantity,
            "billed_qty": line.billed_qty,
            "received_qty": line.received_qty,
            "base_unit": item.base_unit,
            "weight_variance_pct": line.weight_variance_pct,
            "weight_flagged": line.weight_flagged,
            "weight_note": line.weight_note,
        }

    if not with_cost:
        return PurchaseOut(
            **base, lines=[PurchaseLineOut(**line_base(ln)) for ln in purchase.lines]
        )
    return PurchaseOwnerOut(
        **base,
        goods_value=purchase.goods_value,
        gst_amount=purchase.gst_amount,
        charges_total=purchase.charges_total,
        supplier_payable=purchase.supplier_payable,
        lines=[
            PurchaseLineOwnerOut(
                **line_base(ln),
                rate=ln.rate,
                gst_rate=ln.gst_rate,
                goods_value=ln.goods_value,
                gst_amount=ln.gst_amount,
                charges_total=ln.charges_total,
                total_cost=ln.total_cost,
                unit_cost=ln.unit_cost,
                shortage_value=_shortage_value(
                    wc.check_weight(ln.billed_qty, ln.received_qty, Decimal("100")),
                    ln.goods_value,
                    ln.billed_qty,
                ),
                costs=[PurchaseCostOut.model_validate(c) for c in ln.costs],
            )
            for ln in purchase.lines
        ],
    )


def list_purchases(
    db: Session,
    *,
    supplier_id: int | None,
    location_ids: frozenset[int] | None,
    limit: int,
    offset: int,
) -> tuple[list[Purchase], int]:
    filters = [Purchase.tenant_id == TENANT_ID]
    if supplier_id is not None:
        filters.append(Purchase.supplier_id == supplier_id)
    if location_ids is not None:
        filters.append(Purchase.location_id.in_(location_ids))
    total = db.execute(select(func.count()).select_from(Purchase).where(*filters)).scalar_one()
    rows = db.execute(
        select(Purchase)
        .where(*filters)
        .order_by(Purchase.bill_date.desc(), Purchase.id.desc())
        .limit(limit)
        .offset(offset)
    ).scalars()
    return list(rows), total
