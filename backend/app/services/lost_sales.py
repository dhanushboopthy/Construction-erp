"""The lost-sales log and fill rate (FM10, docs/FINANCE_REVIEW.md F26).

Counter staff log "asked for, out of stock" in one step. An entry is permanent (a mistake is
another entry, or ignored). The owner sees each entry valued at the market rate on the day;
counter staff see quantities only. Fill rate = quantity supplied ÷ quantity asked for, where
asked for is what the bills supplied plus what the log says was refused."""

from collections import defaultdict
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
from app.models.masters import Item
from app.models.orders import LostSale
from app.models.sales import SalesInvoice, SalesLine
from app.models.setup import AppUser, Location
from app.schemas.orders import (
    FillRateReport,
    FillRateRow,
    LostSaleCreate,
    LostSaleOut,
    LostSaleOwnerOut,
)
from app.services import items as item_service
from app.services import rates
from app.services.finance import month_bounds


def create(
    db: Session, data: LostSaleCreate, *, actor_id: int, is_owner: bool, can_access: bool
) -> LostSale:
    place = db.get(Location, data.location_id)
    if place is None or place.tenant_id != TENANT_ID or not place.is_active:
        raise NotFoundError("Shop not found", field="location_id")
    if not can_access:
        raise NotFoundError("Shop not found", field="location_id")
    item = db.get(Item, data.item_id)
    if item is None or item.tenant_id != TENANT_ID or not item.is_active:
        raise NotFoundError("Item not found or inactive", field="item_id")
    conversion = item_service.conversions(item).get((data.unit or item.base_unit).lower())
    if conversion is None:
        raise BusinessRuleError(
            f"{item.name} has no unit called {data.unit!r}", code="UNKNOWN_UNIT", field="unit"
        )
    try:
        base = to_base(data.quantity, conversion)
    except ValueError as exc:
        raise BusinessRuleError(str(exc), code="UNIT_NOT_WHOLE", field="quantity") from exc
    today = today_ist()
    on = data.entry_date or today
    if on > today:
        raise BusinessRuleError("An entry cannot be dated in the future", code="FUTURE_DATE")
    if on != today and not is_owner:
        raise BusinessRuleError(
            "Only the owner can enter a lost sale for an earlier day.",
            code="BACKDATE_NEEDS_OWNER",
            field="entry_date",
        )
    board = rates.latest_rates(db, on).get(item.id)
    row = LostSale(
        tenant_id=TENANT_ID,
        location_id=place.id,
        item_id=item.id,
        entry_date=on,
        unit=conversion.unit,
        quantity=data.quantity,
        base_qty=base,
        note=(data.note or "").strip() or None,
        market_rate=board[0].rate if board else None,
        created_by=actor_id,
    )
    db.add(row)
    db.commit()
    return row


def _view(
    row: LostSale,
    items: dict[int, Item],
    places: dict[int, str],
    users: dict[int, str],
    owner: bool,
) -> LostSaleOut | LostSaleOwnerOut:
    item = items[row.item_id]
    common = {
        "id": row.id,
        "location_id": row.location_id,
        "location_code": places.get(row.location_id, ""),
        "entry_date": row.entry_date,
        "item_id": row.item_id,
        "item_name": item.name,
        "unit": row.unit,
        "quantity": row.quantity,
        "base_qty": row.base_qty,
        "base_unit": item.base_unit,
        "note": row.note,
        "entered_by": users.get(row.created_by) if row.created_by else None,
        "entered_at": row.created_at,
    }
    if not owner:
        return LostSaleOut(**common)
    value = money(row.base_qty * row.market_rate) if row.market_rate is not None else None
    return LostSaleOwnerOut(**common, value=value)


def view_one(db: Session, row: LostSale, *, owner: bool) -> LostSaleOut | LostSaleOwnerOut:
    return list_entries(db, row.entry_date, row.entry_date, None, owner=owner, only_id=row.id)[0]


def list_entries(
    db: Session,
    date_from: date,
    date_to: date,
    location_ids: frozenset[int] | None,
    *,
    owner: bool,
    only_id: int | None = None,
) -> list[LostSaleOut | LostSaleOwnerOut]:
    stmt = select(LostSale).where(
        LostSale.tenant_id == TENANT_ID,
        LostSale.entry_date >= date_from,
        LostSale.entry_date <= date_to,
    )
    if location_ids is not None:
        stmt = stmt.where(LostSale.location_id.in_(location_ids))
    if only_id is not None:
        stmt = stmt.where(LostSale.id == only_id)
    rows = db.scalars(stmt.order_by(LostSale.id.desc()).limit(500)).all()
    items = {i.id: i for i in db.scalars(select(Item).where(Item.tenant_id == TENANT_ID))}
    places = {p.id: p.code for p in db.scalars(select(Location))}
    users = {u.id: u.full_name for u in db.scalars(select(AppUser))}
    return [_view(r, items, places, users, owner) for r in rows]


def fill_rate(
    db: Session, period: str, location_ids: frozenset[int] | None, *, owner: bool
) -> FillRateReport:
    date_from, date_to = month_bounds(period)
    if date_from > today_ist():
        raise BusinessRuleError("This month has not started yet", code="FUTURE_PERIOD")
    sold_stmt = (
        select(SalesLine.item_id, func.sum(SalesLine.base_qty), func.count())
        .join(SalesInvoice, SalesInvoice.id == SalesLine.invoice_id)
        .where(
            SalesInvoice.tenant_id == TENANT_ID,
            SalesInvoice.invoice_date >= date_from,
            SalesInvoice.invoice_date <= date_to,
        )
        .group_by(SalesLine.item_id)
    )
    lost_stmt = (
        select(LostSale.item_id, func.sum(LostSale.base_qty), func.count())
        .where(
            LostSale.tenant_id == TENANT_ID,
            LostSale.entry_date >= date_from,
            LostSale.entry_date <= date_to,
        )
        .group_by(LostSale.item_id)
    )
    value_stmt = (
        select(LostSale.item_id, func.sum(LostSale.base_qty * LostSale.market_rate))
        .where(
            LostSale.tenant_id == TENANT_ID,
            LostSale.entry_date >= date_from,
            LostSale.entry_date <= date_to,
            LostSale.market_rate.is_not(None),
        )
        .group_by(LostSale.item_id)
    )
    if location_ids is not None:
        sold_stmt = sold_stmt.where(SalesInvoice.location_id.in_(location_ids))
        lost_stmt = lost_stmt.where(LostSale.location_id.in_(location_ids))
        value_stmt = value_stmt.where(LostSale.location_id.in_(location_ids))
    supplied: dict[int, Decimal] = {}
    lines_supplied = 0
    for item_id, total, n in db.execute(sold_stmt):
        supplied[item_id] = total
        lines_supplied += n
    lost: dict[int, Decimal] = {}
    lines_lost = 0
    for item_id, total, n in db.execute(lost_stmt):
        lost[item_id] = total
        lines_lost += n
    values: dict[int, Decimal] = defaultdict(lambda: ZERO)
    if owner:
        for item_id, total in db.execute(value_stmt):
            values[item_id] = money(total)
    items = {
        i.id: i
        for i in db.scalars(
            select(Item).where(Item.tenant_id == TENANT_ID, Item.id.in_({*supplied, *lost}))
        )
    }
    rows = [
        FillRateRow(
            item_id=item_id,
            item_name=items[item_id].name,
            base_unit=items[item_id].base_unit,
            supplied_qty=qty(supplied.get(item_id, ZERO)),
            lost_qty=qty(lost.get(item_id, ZERO)),
            requested_qty=qty(supplied.get(item_id, ZERO) + lost.get(item_id, ZERO)),
            fill_rate_pct=rules.fill_rate_pct(supplied.get(item_id, ZERO), lost.get(item_id, ZERO)),
            lost_value=values[item_id] if owner else None,
        )
        for item_id in items
    ]
    # Worst-served first: that is where stock-outs cost the most customers.
    rows.sort(key=lambda r: (r.fill_rate_pct is None, r.fill_rate_pct or ZERO, r.item_name))
    return FillRateReport(
        period=period,
        date_from=date_from,
        date_to=date_to,
        location_id=None
        if location_ids is None or len(location_ids) != 1
        else next(iter(location_ids)),
        rows=rows,
        lines_supplied=lines_supplied,
        lines_lost=lines_lost,
        line_fill_rate_pct=rules.fill_rate_pct(lines_supplied, lines_lost),
        lost_value=money(sum(values.values(), ZERO)) if owner else None,
    )
