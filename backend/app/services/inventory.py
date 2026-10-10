"""Inventory analytics, replenishment, stock value and weight shortages (FM6, docs/FINANCE_REVIEW.md
F10 to F14). Everything is rebuilt from the stock ledger, the bills and the rate board on each
request; the only stored thing is a write-down document, which is a real change of value.

Stock adjustments, count corrections, transfers and write-downs are not movement: only a purchase,
a sale or a return moves an item for FSN, aging and cover, so a theft entry cannot make dead stock
look alive."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFoundError
from app.core.tenancy import TENANT_ID
from app.domain import inventory_analytics as ia
from app.domain import stock_valuation as stock_rules
from app.domain.inventory_analytics import Direction
from app.domain.money import ZERO, money
from app.models.enums import DocType, ItemCategory, StockRef
from app.models.ledgers import StockLedger
from app.models.masters import Item, Party
from app.models.purchasing import Purchase, PurchaseLine
from app.models.setup import Location
from app.models.stock_ops import StockWritedown, StockWritedownLine
from app.schemas.inventory import (
    AgeBucketOut,
    FifoAgeOut,
    FifoItemOut,
    FifoLayerOut,
    InventoryAnalyticsOut,
    InventoryRowOut,
    NrvReportOut,
    NrvRowOut,
    ShortageClaimOut,
    ShrinkageOut,
    SupplierShortageOut,
    WritedownCreate,
    WritedownLineOut,
    WritedownOut,
)
from app.services import closing as closing_service
from app.services import ledgers, rates
from app.services.numbering import allocate_number
from app.services.shop_settings import get_settings_row

MOVEMENT = frozenset(
    {
        StockRef.OPENING,
        StockRef.PURCHASE,
        StockRef.PURCHASE_RETURN,
        StockRef.SALE,
        StockRef.SALE_RETURN,
    }
)
VELOCITY_DAYS = 30  # recent pace: cover and reorder
FSN_DAYS = 90  # how often an item sold
MIN_HISTORY_DAYS = 30
AGE_ORDER = ("0-30", "31-90", "91-180", "180+")


def _rows_by_item(db: Session) -> dict[int, list[StockLedger]]:
    out: dict[int, list[StockLedger]] = defaultdict(list)
    rows = db.execute(
        select(StockLedger)
        .where(StockLedger.tenant_id == TENANT_ID)
        .order_by(StockLedger.entry_date, StockLedger.id)
    ).scalars()
    for row in rows:
        out[row.item_id].append(row)
    return out


def _position(rows: list[StockLedger]) -> stock_rules.Replay | None:
    moves = [
        stock_rules.StockMove(r.entry_date, str(r.location_id), r.qty_in, r.qty_out, r.unit_cost)
        for r in rows
    ]
    try:
        return stock_rules.replay(moves)
    except stock_rules.NegativeStockError:
        return None  # the integrity check reports it; an analysis cannot use it


def _active_items(db: Session) -> list[Item]:
    return list(
        db.execute(
            select(Item)
            .where(Item.tenant_id == TENANT_ID, Item.is_active.is_(True))
            .order_by(Item.name)
        ).scalars()
    )


def _last_suppliers(db: Session) -> dict[int, Party]:
    """Each item's most recent supplier: its lead time stands in when the item has none."""
    rows = db.execute(
        select(PurchaseLine.item_id, Purchase.supplier_id)
        .join(Purchase, Purchase.id == PurchaseLine.purchase_id)
        .where(Purchase.tenant_id == TENANT_ID)
        .order_by(Purchase.bill_date, Purchase.id)
    ).all()
    latest = dict(rows)  # the last purchase of each item wins
    parties = {
        p.id: p for p in db.execute(select(Party).where(Party.tenant_id == TENANT_ID)).scalars()
    }
    return {item_id: parties[sid] for item_id, sid in latest.items() if sid in parties}


# ------------------------------------------------------------------------------ analytics


@dataclass
class _Shelf:
    """One item's stock and selling facts, before classes and reorder points are worked out."""

    item: Item
    on_hand: Decimal
    avg_cost: Decimal
    value: Decimal
    last_movement: date | None
    days_sold: int
    consumption: Decimal  # cost of what sold in the last 90 days
    qty30: Decimal  # sold in the last 30 days


def analytics(db: Session, today: date) -> InventoryAnalyticsOut:
    settings = get_settings_row(db)
    ledger = _rows_by_item(db)
    suppliers = _last_suppliers(db)
    activity = [
        r.entry_date
        for rows in ledger.values()
        for r in rows
        if r.ref_type in (StockRef.SALE, StockRef.PURCHASE)
    ]
    first = min(activity) if activity else None
    enough = ia.has_history(first, today, MIN_HISTORY_DAYS)
    history_days = (today - first).days + 1 if first else 0

    shelves: list[_Shelf] = []
    for item in _active_items(db):
        rows = ledger.get(item.id, [])
        pos = _position(rows)
        if pos is None:
            continue
        on_hand = sum(pos.by_location.values(), ZERO)
        sales = [r for r in rows if r.ref_type is StockRef.SALE]
        recent = [r for r in sales if r.entry_date > today - timedelta(days=FSN_DAYS)]
        if on_hand <= ZERO and not recent:
            continue  # nothing on the shelf and nothing sold lately: not worth a row
        moved = [r.entry_date for r in rows if r.ref_type in MOVEMENT]
        shelves.append(
            _Shelf(
                item=item,
                on_hand=on_hand,
                avg_cost=pos.total.avg_cost,
                value=money(on_hand * pos.total.avg_cost) if on_hand > ZERO else money(ZERO),
                last_movement=max(moved) if moved else None,
                days_sold=len({r.entry_date for r in recent}),
                consumption=money(sum((r.qty_out * r.unit_cost for r in recent), ZERO)),
                qty30=sum(
                    (
                        r.qty_out
                        for r in sales
                        if r.entry_date > today - timedelta(days=VELOCITY_DAYS)
                    ),
                    ZERO,
                ),
            )
        )
    classes = ia.abc_classes({x.item.name: x.consumption for x in shelves}) if enough else {}

    out: list[InventoryRowOut] = []
    buckets = dict.fromkeys(AGE_ORDER, ZERO)
    counts = dict.fromkeys(AGE_ORDER, 0)
    for x in shelves:
        age = (today - x.last_movement).days if x.last_movement else None
        bucket = ia.age_bucket(age) if age is not None and x.on_hand > ZERO else None
        if bucket is not None:
            buckets[bucket] += x.value
            counts[bucket] += 1
        daily = ia.average_daily_sales(x.qty30, VELOCITY_DAYS) if enough else None
        supplier = suppliers.get(x.item.id)
        lead = ia.pick_days(
            item=x.item.lead_time_days,
            supplier=supplier.lead_time_days if supplier else None,
            default=settings.default_lead_time_days,
        )
        safety = ia.pick_days(
            item=x.item.safety_days, supplier=None, default=settings.default_safety_days
        )
        point = (
            ia.reorder_point(daily, lead, safety) if daily is not None and daily > ZERO else None
        )
        out.append(
            InventoryRowOut(
                item_id=x.item.id,
                item_name=x.item.name,
                category=x.item.category,
                base_unit=x.item.base_unit,
                on_hand=x.on_hand,
                avg_cost=x.avg_cost,
                value=x.value,
                last_movement=x.last_movement,
                age_days=age,
                age_bucket=bucket,
                days_sold=x.days_sold,
                consumption=x.consumption,
                abc=classes.get(x.item.name),
                fsn=ia.fsn_class(x.days_sold, fast_min_days=settings.fsn_fast_min_days)
                if enough
                else None,
                avg_daily_sales=daily,
                cover_days=ia.cover_days(x.on_hand, daily) if daily is not None else None,
                lead_days=lead,
                safety_days=safety,
                reorder_point=point,
                short_by=ia.short_by(x.on_hand, point) if point is not None else None,
                reorder_now=point is not None and ia.needs_reorder(x.on_hand, point),
            )
        )
    out.sort(key=lambda r: (not r.reorder_now, -r.consumption, r.item_name))
    note = (
        None
        if enough
        else f"Not enough data yet (needs {MIN_HISTORY_DAYS} days of bills; there are "
        f"{history_days}). Stock age is shown; classes, cover and reorder points wait."
    )
    return InventoryAnalyticsOut(
        as_of=today,
        history_days=history_days,
        enough_data=enough,
        data_note=note,
        default_lead_days=settings.default_lead_time_days,
        default_safety_days=settings.default_safety_days,
        fsn_fast_min_days=settings.fsn_fast_min_days,
        stock_value=money(sum((r.value for r in out), ZERO)),
        dead_stock_value=money(buckets["180+"]),
        aging=[AgeBucketOut(bucket=b, value=money(buckets[b]), items=counts[b]) for b in AGE_ORDER],
        rows=out,
    )


# ------------------------------------------------------------------------------ value (NRV)


def _replacement_costs(db: Session) -> dict[int, Decimal]:
    rows = db.execute(
        select(PurchaseLine.item_id, PurchaseLine.unit_cost)
        .join(Purchase, Purchase.id == PurchaseLine.purchase_id)
        .where(Purchase.tenant_id == TENANT_ID)
        .order_by(Purchase.bill_date, Purchase.id, PurchaseLine.id)
    ).all()
    return dict(rows)  # the last purchase of each item wins


def nrv_report(db: Session, today: date) -> NrvReportOut:
    settings = get_settings_row(db)
    ledger = _rows_by_item(db)
    board = rates.latest_rates(db, today)
    replacement = _replacement_costs(db)
    out: list[NrvRowOut] = []
    for item in _active_items(db):
        pos = _position(ledger.get(item.id, []))
        if pos is None:
            continue
        on_hand = sum(pos.by_location.values(), ZERO)
        if on_hand <= ZERO:
            continue
        avg = pos.total.avg_cost
        current = board.get(item.id, [None])[0]
        nrv = ia.nrv_per_unit(current.rate, settings.nrv_selling_cost_pct) if current else None
        cost_now = replacement.get(item.id)
        out.append(
            NrvRowOut(
                item_id=item.id,
                item_name=item.name,
                base_unit=item.base_unit,
                on_hand=on_hand,
                avg_cost=avg,
                value=money(on_hand * avg),
                market_rate=current.rate if current else None,
                market_date=current.effective_date if current else None,
                nrv=nrv,
                nrv_loss=ia.nrv_loss(on_hand, avg, nrv) if nrv is not None else money(ZERO),
                replacement_cost=cost_now,
                holding_gain_loss=ia.holding_gain_loss(on_hand, avg, cost_now)
                if cost_now is not None
                else None,
            )
        )
    out.sort(key=lambda r: (-r.nrv_loss, r.item_name))
    return NrvReportOut(
        as_of=today,
        cost_to_sell_pct=settings.nrv_selling_cost_pct,
        writedown_enabled=settings.nrv_writedown_enabled,
        stock_value=money(sum((r.value for r in out), ZERO)),
        nrv_loss=money(sum((r.nrv_loss for r in out), ZERO)),
        holding_gain_loss=money(sum((r.holding_gain_loss or ZERO for r in out), ZERO)),
        rows=out,
    )


def _writedown_view(db: Session, doc: StockWritedown) -> WritedownOut:
    names = {i.id: i for i in db.execute(select(Item).where(Item.tenant_id == TENANT_ID)).scalars()}
    lines = [
        WritedownLineOut(
            item_id=ln.item_id,
            item_name=names[ln.item_id].name,
            base_unit=names[ln.item_id].base_unit,
            quantity=ln.quantity,
            old_cost=ln.old_cost,
            new_cost=ln.new_cost,
            market_rate=ln.market_rate,
            value=ln.value,
        )
        for ln in doc.lines
    ]
    return WritedownOut(
        id=doc.id,
        number=doc.number,
        location_id=doc.location_id,
        writedown_date=doc.writedown_date,
        note=doc.note,
        total=money(sum((ln.value for ln in lines), ZERO)),
        lines=lines,
    )


def create_writedown(
    db: Session, data: WritedownCreate, *, today: date, actor_id: int
) -> WritedownOut:
    """Lower the stock of the chosen items to today's net realisable value. Owner only. Quantities
    do not change and no input tax is reversed: the goods are still there."""
    settings = get_settings_row(db)
    if not settings.nrv_writedown_enabled:
        raise BusinessRuleError(
            "Writing stock down to market value is switched off in Settings. Ask your accountant.",
            code="WRITEDOWN_DISABLED",
        )
    place = db.get(Location, data.location_id)
    if place is None or place.tenant_id != TENANT_ID or not place.is_active:
        raise NotFoundError("Shop not found", field="location_id")
    if len(set(data.item_ids)) != len(data.item_ids):
        raise BusinessRuleError("An item is listed twice", code="DUPLICATE_ITEM", field="item_ids")
    closing_service.ensure_day_open(db, place.id, today)
    ledgers.lock_items(db, set(data.item_ids))
    board = rates.latest_rates(db, today)
    prepared: list[tuple[Item, stock_rules.Replay, Decimal, Decimal]] = []
    for item_id in data.item_ids:
        item = db.get(Item, item_id)
        if item is None or item.tenant_id != TENANT_ID:
            raise NotFoundError("Item not found", field="item_ids")
        pos = _position(
            list(
                db.execute(
                    select(StockLedger)
                    .where(StockLedger.tenant_id == TENANT_ID, StockLedger.item_id == item.id)
                    .order_by(StockLedger.entry_date, StockLedger.id)
                ).scalars()
            )
        )
        current = board.get(item.id, [None])[0]
        if current is None:
            raise BusinessRuleError(
                f"{item.name} has no market rate, so its realisable value is not known.",
                code="NO_MARKET_RATE",
                field="item_ids",
            )
        nrv = ia.nrv_per_unit(current.rate, settings.nrv_selling_cost_pct)
        quantity = sum(pos.by_location.values(), ZERO) if pos else ZERO
        if (
            pos is None
            or quantity <= ZERO
            or ia.nrv_loss(quantity, pos.total.avg_cost, nrv) <= ZERO
        ):
            raise BusinessRuleError(
                f"{item.name} is not worth less than it cost today, so there is nothing to write "
                "down.",
                code="NOTHING_TO_WRITE_DOWN",
                field="item_ids",
            )
        prepared.append((item, pos, nrv, current.rate))

    number = allocate_number(
        db,
        location_id=place.id,
        doc_type=DocType.STOCK_WRITEDOWN,
        on=today,
        fy_start_month=settings.financial_year_start_month,
    )
    doc = StockWritedown(
        tenant_id=TENANT_ID,
        number=number,
        location_id=place.id,
        writedown_date=today,
        note=(data.note or "").strip() or None,
        created_by=actor_id,
    )
    db.add(doc)
    db.flush()
    for item, pos, nrv, rate in prepared:
        quantity = sum(pos.by_location.values(), ZERO)
        old = pos.total.avg_cost
        held = {place_id: q for place_id, q in pos.by_location.items() if q > ZERO}
        for move in ia.writedown_moves(held, old, nrv):
            ledgers.add_stock_move(
                db,
                item_id=item.id,
                location_id=int(move.place),
                entry_date=today,
                qty_in=move.quantity if move.direction is Direction.IN else ZERO,
                qty_out=move.quantity if move.direction is Direction.OUT else ZERO,
                unit_cost=move.unit_cost,
                ref_type=StockRef.STOCK_WRITEDOWN,
                ref_id=doc.id,
                narration=f"Write-down {number}: {item.name} to {nrv}",
                actor_id=actor_id,
            )
        doc.lines.append(
            StockWritedownLine(
                tenant_id=TENANT_ID,
                item_id=item.id,
                quantity=quantity,
                old_cost=old,
                new_cost=nrv,
                market_rate=rate,
                value=ia.writedown_value(quantity, old, nrv),
            )
        )
    db.commit()
    return _writedown_view(db, doc)


def list_writedowns(
    db: Session, date_from: date | None, date_to: date | None
) -> list[WritedownOut]:
    stmt = select(StockWritedown).where(StockWritedown.tenant_id == TENANT_ID)
    if date_from is not None:
        stmt = stmt.where(StockWritedown.writedown_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(StockWritedown.writedown_date <= date_to)
    return [
        _writedown_view(db, d)
        for d in db.execute(stmt.order_by(StockWritedown.id.desc())).scalars()
    ]


def written_down(db: Session, date_from: date, date_to: date, location_id: int | None) -> Decimal:
    """Stock written down to NRV in a period, for the profit and loss."""
    stmt = (
        select(StockWritedownLine.value)
        .join(StockWritedown, StockWritedown.id == StockWritedownLine.writedown_id)
        .where(
            StockWritedown.tenant_id == TENANT_ID,
            StockWritedown.writedown_date >= date_from,
            StockWritedown.writedown_date <= date_to,
        )
    )
    if location_id is not None:
        stmt = stmt.where(StockWritedown.location_id == location_id)
    return money(sum(db.execute(stmt).scalars(), ZERO))


# ------------------------------------------------------------------------------ cement age


def fifo_age(db: Session, today: date) -> FifoAgeOut:
    ledger = _rows_by_item(db)
    out: list[FifoItemOut] = []
    for item in _active_items(db):
        if item.category is not ItemCategory.CEMENT:
            continue
        rows = [
            r
            for r in ledger.get(item.id, [])
            if r.ref_type not in (StockRef.TRANSFER, StockRef.STOCK_WRITEDOWN)
        ]
        layers = ia.fifo_layers([ia.FifoMove(r.entry_date, r.qty_in, r.qty_out) for r in rows])
        if not layers:
            continue
        pos = _position(ledger.get(item.id, []))
        avg = pos.total.avg_cost if pos else ZERO
        buckets = ia.layer_buckets(layers, today)
        out.append(
            FifoItemOut(
                item_id=item.id,
                item_name=item.name,
                base_unit=item.base_unit,
                on_hand=sum((x.quantity for x in layers), ZERO),
                oldest_age_days=max(x.age_days(today) for x in layers),
                buckets=buckets,
                over_90_value=money(buckets["90+"] * avg),
                layers=[
                    FifoLayerOut(
                        received=x.received, quantity=x.quantity, age_days=x.age_days(today)
                    )
                    for x in layers
                ],
            )
        )
    out.sort(key=lambda r: -(r.oldest_age_days or 0))
    return FifoAgeOut(
        as_of=today,
        note="An estimate: stock is taken to be sold oldest first, from the days it came in. "
        "Cement has no lot numbers here yet.",
        items=out,
    )


# ------------------------------------------------------------------------------ shrinkage


@dataclass
class _Supplier:
    name: str
    lines: int = 0
    goods: Decimal = ZERO
    short: Decimal = ZERO
    short_lines: int = 0


def shrinkage(db: Session, date_from: date, date_to: date) -> ShrinkageOut:
    if date_to < date_from:
        raise BusinessRuleError(
            "The end date is before the start date", code="BAD_RANGE", field="date_to"
        )
    rows = db.execute(
        select(PurchaseLine, Purchase, Party, Item)
        .join(Purchase, Purchase.id == PurchaseLine.purchase_id)
        .join(Party, Party.id == Purchase.supplier_id)
        .join(Item, Item.id == PurchaseLine.item_id)
        .where(
            Purchase.tenant_id == TENANT_ID,
            Purchase.bill_date >= date_from,
            Purchase.bill_date <= date_to,
        )
        .order_by(Purchase.bill_date, Purchase.id, PurchaseLine.line_no)
    ).all()
    per: dict[int, _Supplier] = {}
    claims: list[ShortageClaimOut] = []
    for line, purchase, supplier, item in rows:
        value = ia.shortage_value(line.billed_qty, line.received_qty, line.goods_value)
        entry = per.setdefault(supplier.id, _Supplier(supplier.name))
        entry.lines += 1
        entry.goods += line.goods_value
        entry.short += value
        if line.received_qty < line.billed_qty:
            entry.short_lines += 1
            pct = ia.weight_loss_pct(line.billed_qty, line.received_qty)
            claims.append(
                ShortageClaimOut(
                    purchase_number=purchase.number,
                    bill_no=purchase.bill_no,
                    bill_date=purchase.bill_date,
                    party_name=supplier.name,
                    item_name=item.name,
                    base_unit=item.base_unit,
                    billed_qty=line.billed_qty,
                    received_qty=line.received_qty,
                    shortage_qty=line.billed_qty - line.received_qty,
                    loss_pct=pct if pct is not None else ZERO,
                    value=value,
                )
            )
    suppliers = [
        SupplierShortageOut(
            party_id=pid,
            party_name=e.name,
            lines=e.lines,
            goods_value=money(e.goods),
            shortage_value=money(e.short),
            shortage_pct=ia.weight_loss_pct(e.goods, e.goods - e.short),
            short_lines=e.short_lines,
        )
        for pid, e in per.items()
    ]
    suppliers.sort(key=lambda s: (-s.shortage_value, s.party_name))
    claims.sort(key=lambda c: -c.value)
    return ShrinkageOut(
        date_from=date_from,
        date_to=date_to,
        shortage_value=money(sum((s.shortage_value for s in suppliers), ZERO)),
        suppliers=suppliers,
        claims=claims,
    )
