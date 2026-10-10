"""Stock adjustments with a reason (FM2, docs/FINANCE_REVIEW.md F3, F15).

Breakage, rust, theft, weighbridge differences, free samples and count corrections each get
their own document and a reason on every stock ledger row they write, so losses are visible
by cause instead of hiding in "count corrections". Counter staff above the owner's limit need
the owner's PIN. Goods lost carry input tax credit that has to be reversed in GSTR-3B; the
"ITC to reverse" list is worked out from the ledger rows, never stored."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import today_ist
from app.core.errors import BusinessRuleError, NotFoundError, PermissionDeniedError
from app.core.tenancy import TENANT_ID
from app.domain import inventory_analytics as ia
from app.domain.finance import needs_approval
from app.domain.inventory_analytics import AdjustmentReason, Direction
from app.domain.money import ZERO, money
from app.domain.stock_valuation import NegativeStockError, ensure_available
from app.models.approvals import Approval
from app.models.enums import ApprovalAction, DocType, Role, StockRef
from app.models.ledgers import StockLedger
from app.models.masters import Item
from app.models.setup import AppUser, Location
from app.models.stock_ops import StockAdjustment, StockAdjustmentLine
from app.schemas.stock_ops import (
    AdjustmentBookOut,
    AdjustmentBookOwnerOut,
    AdjustmentCreate,
    AdjustmentLineOut,
    AdjustmentLineOwnerOut,
    AdjustmentOut,
    AdjustmentOwnerOut,
    ItcReversalOut,
    ItcReversalRow,
    ReasonTotal,
)
from app.services import approvals as approval_service
from app.services import closing as closing_service
from app.services import ledgers
from app.services.cashbook import Actor
from app.services.numbering import allocate_number
from app.services.shop_settings import get_settings_row
from app.services.stock_ops import base_quantity

ADJUSTMENT_REFS = (StockRef.ADJUSTMENT, StockRef.STOCK_ADJUSTMENT)


# ---------------------------------------------------------------------------- writing


def _approval(db: Session, ids: list[int], actor: Actor) -> Approval | None:
    if not ids:
        return None
    found = approval_service.load_valid(db, ids, actor.user_id, party_id=0)
    match = next((a for a in found if a.action is ApprovalAction.STOCK_ADJUSTMENT), None)
    if match is None:
        raise BusinessRuleError(
            "That approval is not for a stock adjustment. Ask the owner again.",
            code="APPROVAL_INVALID",
            requires_owner_approval=True,
        )
    return match


@dataclass(frozen=True)
class _Line:
    item: Item
    direction: Direction
    quantity: Decimal  # base units


def _lines(db: Session, data: AdjustmentCreate) -> list[_Line]:
    allowed = ia.allowed_directions(data.reason)
    label = ia.REASON_LABELS[data.reason]
    out: list[_Line] = []
    seen: set[int] = set()
    for line in data.lines:
        item, qty = base_quantity(db, line.item_id, line.quantity, line.unit)
        if item.id in seen:
            raise BusinessRuleError(
                f"{item.name} is listed twice. Put it on one line.",
                code="DUPLICATE_ITEM",
                field="item_id",
            )
        seen.add(item.id)
        direction = line.direction or ia.default_direction(data.reason)
        if direction is None:
            raise BusinessRuleError(
                f"{item.name}: say whether the count found more or less.",
                code="DIRECTION_REQUIRED",
                field="direction",
            )
        if direction not in allowed:
            way = "add stock" if direction is Direction.IN else "remove stock"
            raise BusinessRuleError(
                f"{label} cannot {way}.", code="WRONG_DIRECTION", field="direction"
            )
        out.append(_Line(item, direction, qty))
    return out


def create_adjustment(
    db: Session, data: AdjustmentCreate, actor: Actor
) -> AdjustmentOut | AdjustmentOwnerOut:
    if actor.role is Role.ACCOUNTANT:
        raise PermissionDeniedError("The accountant can read stock adjustments but not post them")
    owner = actor.role is Role.OWNER
    if not actor.can_access:
        raise PermissionDeniedError("You can only adjust the stock of your own shop")
    place = db.get(Location, data.location_id)
    if place is None or place.tenant_id != TENANT_ID or not place.is_active:
        raise NotFoundError("Location not found or inactive", field="location_id")

    today = today_ist()
    on = data.adjustment_date or today
    if on > today:
        raise BusinessRuleError("An adjustment cannot be dated in the future", code="FUTURE_DATE")
    if on != today and not owner:
        raise BusinessRuleError(
            "Only the owner can enter an adjustment for an earlier day.",
            code="BACKDATE_NEEDS_OWNER",
            field="adjustment_date",
        )
    closing_service.ensure_day_open(db, place.id, on)

    lines = _lines(db, data)
    ledgers.lock_items(db, {x.item.id for x in lines})
    costs: dict[int, Decimal] = {}
    for x in lines:
        position, here = ledgers.stock_position(db, x.item.id, place.id)
        costs[x.item.id] = position.avg_cost
        if x.direction is Direction.OUT:
            try:
                ensure_available(here, x.quantity)
            except NegativeStockError as exc:
                raise BusinessRuleError(
                    f"{x.item.name}: {exc}", code="INSUFFICIENT_STOCK", field="quantity"
                ) from exc

    approval = None
    if not owner:
        limit = get_settings_row(db).adjustment_approval_limit
        approval = _approval(db, data.approval_ids, actor)
        # Gross, not net: a count that finds 10 bags more of one item and 10 fewer of another
        # still moves stock worth checking.
        gross = sum((ia.move_value(x.quantity, costs[x.item.id]) for x in lines), ZERO)
        if approval is None and needs_approval(gross, limit):
            raise BusinessRuleError(
                f"Adjustments worth more than ₹{limit:,.0f} need the owner's approval.",
                code="ADJUSTMENT_NEEDS_OWNER",
                requires_owner_approval=True,
            )

    settings = get_settings_row(db)
    number = allocate_number(
        db,
        location_id=place.id,
        doc_type=DocType.STOCK_ADJUSTMENT,
        on=on,
        fy_start_month=settings.financial_year_start_month,
    )
    row = StockAdjustment(
        tenant_id=TENANT_ID,
        number=number,
        location_id=place.id,
        adjustment_date=on,
        reason=data.reason,
        note=(data.note or "").strip() or None,
        approval_id=approval.id if approval else None,
        created_by=actor.user_id,
        lines=[
            StockAdjustmentLine(
                tenant_id=TENANT_ID,
                item_id=x.item.id,
                direction=x.direction,
                quantity=x.quantity,
                unit_cost=costs[x.item.id],
            )
            for x in lines
        ],
    )
    db.add(row)
    db.flush()
    for x in lines:
        ledgers.add_stock_move(
            db,
            item_id=x.item.id,
            location_id=place.id,
            entry_date=on,
            qty_in=x.quantity if x.direction is Direction.IN else ZERO,
            qty_out=x.quantity if x.direction is Direction.OUT else ZERO,
            unit_cost=costs[x.item.id],
            ref_type=StockRef.STOCK_ADJUSTMENT,
            ref_id=row.id,
            narration=f"{ia.REASON_LABELS[data.reason]} {number}",
            reason=data.reason,
            actor_id=actor.user_id,
        )
    if approval is not None:
        approval_service.mark_used([approval], number)
    db.commit()
    return _views(db, [row], with_cost=owner)[0]


# ---------------------------------------------------------------------------- reading


def _views(
    db: Session, rows: list[StockAdjustment], *, with_cost: bool
) -> list[AdjustmentOut] | list[AdjustmentOwnerOut]:
    if not rows:
        return []
    items = {i.id: i for i in db.execute(select(Item).where(Item.tenant_id == TENANT_ID)).scalars()}
    codes = dict(db.execute(select(Location.id, Location.code)).all())
    users = dict(db.execute(select(AppUser.id, AppUser.full_name)).all())
    reverse_shortages = get_settings_row(db).itc_reverse_shortages
    plain: list[AdjustmentOut] = []
    costed: list[AdjustmentOwnerOut] = []
    for r in rows:
        base = {
            "id": r.id,
            "number": r.number,
            "location_id": r.location_id,
            "location_code": codes.get(r.location_id, ""),
            "adjustment_date": r.adjustment_date,
            "reason": r.reason,
            "reason_label": ia.REASON_LABELS[r.reason],
            "note": r.note,
            "approved": r.approval_id is not None,
            "created_by_name": users.get(r.created_by) if r.created_by else None,
        }
        if not with_cost:
            plain.append(
                AdjustmentOut(
                    **base,
                    lines=[
                        AdjustmentLineOut(
                            item_id=x.item_id,
                            item_name=items[x.item_id].name,
                            base_unit=items[x.item_id].base_unit,
                            direction=x.direction,
                            quantity=x.quantity,
                        )
                        for x in r.lines
                    ],
                )
            )
            continue
        moves = [
            ia.AdjustmentMove(
                r.reason, x.direction, x.quantity, x.unit_cost, items[x.item_id].gst_rate
            )
            for x in r.lines
        ]
        costed.append(
            AdjustmentOwnerOut(
                **base,
                lines=[
                    AdjustmentLineOwnerOut(
                        item_id=x.item_id,
                        item_name=items[x.item_id].name,
                        base_unit=items[x.item_id].base_unit,
                        direction=x.direction,
                        quantity=x.quantity,
                        unit_cost=x.unit_cost,
                        value=m.loss,
                    )
                    for x, m in zip(r.lines, moves, strict=True)
                ],
                value=ia.net_stock_loss(moves),
                itc_to_reverse=ia.total_itc_to_reverse(moves, reverse_shortages=reverse_shortages),
            )
        )
    return costed if with_cost else plain


def get_adjustment(db: Session, adjustment_id: int) -> StockAdjustment:
    row = db.get(StockAdjustment, adjustment_id)
    if row is None or row.tenant_id != TENANT_ID:
        raise NotFoundError("Adjustment not found")
    return row


def adjustment_view(
    db: Session, row: StockAdjustment, *, with_cost: bool
) -> AdjustmentOut | AdjustmentOwnerOut:
    return _views(db, [row], with_cost=with_cost)[0]


def adjustment_book(
    db: Session,
    *,
    location_ids: frozenset[int] | None,
    location_id: int | None,
    date_from: date,
    date_to: date,
    with_cost: bool,
) -> AdjustmentBookOut | AdjustmentBookOwnerOut:
    if date_to < date_from:
        raise BusinessRuleError("The end date is before the start date", code="BAD_RANGE")
    stmt = select(StockAdjustment).where(
        StockAdjustment.tenant_id == TENANT_ID,
        StockAdjustment.adjustment_date >= date_from,
        StockAdjustment.adjustment_date <= date_to,
    )
    if location_id is not None:
        stmt = stmt.where(StockAdjustment.location_id == location_id)
    if location_ids is not None:
        stmt = stmt.where(StockAdjustment.location_id.in_(location_ids))
    rows = list(
        db.execute(
            stmt.order_by(StockAdjustment.adjustment_date.desc(), StockAdjustment.id.desc())
        ).scalars()
    )
    views = _views(db, rows, with_cost=with_cost)
    if not with_cost:
        return AdjustmentBookOut(
            date_from=date_from,
            date_to=date_to,
            location_id=location_id,
            entries=[v for v in views if isinstance(v, AdjustmentOut)],
        )
    # Counts posted in the range are adjustments too: the totals include them.
    moves = [m for m, _ in adjustment_moves(db, date_from, date_to, location_id)]
    reverse_shortages = get_settings_row(db).itc_reverse_shortages
    return AdjustmentBookOwnerOut(
        date_from=date_from,
        date_to=date_to,
        location_id=location_id,
        entries=[v for v in views if isinstance(v, AdjustmentOwnerOut)],
        by_reason=[
            ReasonTotal(reason=reason, reason_label=ia.REASON_LABELS[reason], value=value)
            for reason, value in ia.loss_by_reason(moves).items()
        ],
        net_loss=ia.net_stock_loss(moves),
        itc_to_reverse=ia.total_itc_to_reverse(moves, reverse_shortages=reverse_shortages),
    )


# ---------------------------------------------------------------------------- figures


def adjustment_moves(
    db: Session, date_from: date, date_to: date, location_id: int | None = None
) -> list[tuple[ia.AdjustmentMove, StockLedger]]:
    """Every adjustment ledger row in the range, documents and posted counts alike. Counts
    posted before FM2 have no reason: they were count corrections."""
    stmt = (
        select(StockLedger, Item.gst_rate)
        .join(Item, Item.id == StockLedger.item_id)
        .where(
            StockLedger.tenant_id == TENANT_ID,
            StockLedger.ref_type.in_(ADJUSTMENT_REFS),
            StockLedger.entry_date >= date_from,
            StockLedger.entry_date <= date_to,
        )
        .order_by(StockLedger.entry_date, StockLedger.id)
    )
    if location_id is not None:
        stmt = stmt.where(StockLedger.location_id == location_id)
    out = []
    for row, gst_rate in db.execute(stmt).all():
        outward = row.qty_out > ZERO
        move = ia.AdjustmentMove(
            row.reason or AdjustmentReason.COUNT_CORRECTION,
            Direction.OUT if outward else Direction.IN,
            row.qty_out if outward else row.qty_in,
            row.unit_cost,
            gst_rate,
        )
        out.append((move, row))
    return out


def stock_loss(db: Session, date_from: date, date_to: date, location_id: int | None) -> Decimal:
    """Net stock value lost through adjustments in the range, for the profit and loss."""
    return ia.net_stock_loss(m for m, _ in adjustment_moves(db, date_from, date_to, location_id))


def itc_reversal(db: Session, period: str) -> ItcReversalOut:
    """Input tax to take back in GSTR-3B table 4(B)(1) for goods lost in the month."""
    from app.services.finance import month_bounds  # finance imports this module

    date_from, date_to = month_bounds(period)
    settings = get_settings_row(db)
    shortages = settings.itc_reverse_shortages
    items = {i.id: i for i in db.execute(select(Item).where(Item.tenant_id == TENANT_ID)).scalars()}
    codes = dict(db.execute(select(Location.id, Location.code)).all())
    numbers = dict(
        db.execute(
            select(StockAdjustment.id, StockAdjustment.number).where(
                StockAdjustment.tenant_id == TENANT_ID
            )
        ).all()
    )
    rows: list[ItcReversalRow] = []
    for move, ledger_row in adjustment_moves(db, date_from, date_to):
        if not ia.itc_reversible(move.reason, move.direction, reverse_shortages=shortages):
            continue
        item = items[ledger_row.item_id]
        document = (
            numbers.get(ledger_row.ref_id or 0, "")
            if ledger_row.ref_type is StockRef.STOCK_ADJUSTMENT
            else f"Count {ledger_row.ref_id}"
        )
        rows.append(
            ItcReversalRow(
                entry_date=ledger_row.entry_date,
                document=document,
                location_code=codes.get(ledger_row.location_id, ""),
                item_name=item.name,
                hsn=item.hsn,
                reason=move.reason,
                reason_label=ia.REASON_LABELS[move.reason],
                quantity=move.quantity,
                base_unit=item.base_unit,
                value=move.value,
                gst_rate=move.gst_rate,
                itc=ia.itc_to_reverse(move.value, move.gst_rate),
            )
        )
    note = (
        "Goods lost, stolen, destroyed or given as free samples (CGST Act s.17(5)(h))"
        + (", and unexplained shortages" if shortages else "")
        + ", at their cost x the item's GST rate. Report the total in GSTR-3B 4(B)(1); your "
        "accountant splits it into CGST, SGST and IGST as the credit was taken."
    )
    return ItcReversalOut(
        period=period,
        date_from=date_from,
        date_to=date_to,
        includes_shortages=shortages,
        rows=rows,
        total_value=money(sum((r.value for r in rows), ZERO)),
        total_itc=money(sum((r.itc for r in rows), ZERO)),
        note=note,
    )
