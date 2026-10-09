"""Stock transfers and physical counts (Milestone 4, rules B13 and G6)."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import today_ist
from app.core.errors import BusinessRuleError, NotFoundError, PermissionDeniedError
from app.core.tenancy import TENANT_ID
from app.domain.money import ZERO, money
from app.domain.stock_valuation import NegativeStockError, count_variance, ensure_available
from app.domain.units import to_base
from app.models.enums import CountStatus, DocType, StockRef
from app.models.ledgers import StockLedger
from app.models.masters import Item
from app.models.setup import Location
from app.models.stock_ops import StockCount, StockCountLine, StockTransfer, StockTransferLine
from app.schemas.stock_ops import (
    CountCreate,
    CountLineOut,
    CountLineOwnerOut,
    CountLinesUpdate,
    CountOut,
    CountOwnerOut,
    TransferCreate,
    TransferLineOut,
    TransferOut,
)
from app.services import items as item_service
from app.services import ledgers
from app.services.numbering import allocate_number
from app.services.shop_settings import get_settings_row


def _location(db: Session, location_id: int, field: str) -> Location:
    row = db.get(Location, location_id)
    if row is None or row.tenant_id != TENANT_ID or not row.is_active:
        raise NotFoundError("Location not found or inactive", field=field)
    return row


# ---------------------------------------------------------------------------- transfers


def _transfer_view(db: Session, t: StockTransfer) -> TransferOut:
    codes = {
        loc.id: loc.code
        for loc in db.execute(
            select(Location).where(Location.id.in_([t.from_location_id, t.to_location_id]))
        ).scalars()
    }
    items = {i.id: i for i in db.execute(select(Item)).scalars()}
    return TransferOut(
        id=t.id,
        number=t.number,
        from_location_id=t.from_location_id,
        from_code=codes[t.from_location_id],
        to_location_id=t.to_location_id,
        to_code=codes[t.to_location_id],
        transfer_date=t.transfer_date,
        note=t.note,
        lines=[
            TransferLineOut(
                item_id=line.item_id,
                item_name=items[line.item_id].name,
                base_unit=items[line.item_id].base_unit,
                quantity=line.quantity,
            )
            for line in t.lines
        ],
    )


def create_transfer(
    db: Session, data: TransferCreate, *, actor_id: int, can_access_from: bool
) -> TransferOut:
    if not can_access_from:
        raise PermissionDeniedError("You can only move stock out of your own shop")
    origin = _location(db, data.from_location_id, "from_location_id")
    target = _location(db, data.to_location_id, "to_location_id")
    on = data.transfer_date or today_ist()

    wanted: dict[int, Decimal] = {}
    for line in data.lines:
        item = db.get(Item, line.item_id)
        if item is None or item.tenant_id != TENANT_ID or not item.is_active:
            raise NotFoundError("Item not found or inactive", field="item_id")
        conversion = item_service.conversions(item).get((line.unit or item.base_unit).lower())
        if conversion is None:
            raise BusinessRuleError(
                f"{item.name} has no unit called {line.unit!r}", code="UNKNOWN_UNIT", field="unit"
            )
        try:
            wanted[item.id] = wanted.get(item.id, ZERO) + to_base(line.quantity, conversion)
        except ValueError as exc:
            raise BusinessRuleError(str(exc), code="UNIT_NOT_WHOLE", field="quantity") from exc

    # Rule B13: check the origin holds enough of every item before moving anything.
    ledgers.lock_items(db, set(wanted))
    positions = {}
    for item_id, base_qty in wanted.items():
        position, at_origin = ledgers.stock_position(db, item_id, origin.id)
        positions[item_id] = position
        try:
            ensure_available(at_origin, base_qty)
        except NegativeStockError as exc:
            name = db.get(Item, item_id).name  # type: ignore[union-attr]
            raise BusinessRuleError(
                f"{name}: {exc}", code="INSUFFICIENT_STOCK", field="quantity"
            ) from exc

    settings = get_settings_row(db)
    number = allocate_number(
        db,
        location_id=origin.id,
        doc_type=DocType.DELIVERY_CHALLAN,
        on=on,
        fy_start_month=settings.financial_year_start_month,
    )
    transfer = StockTransfer(
        tenant_id=TENANT_ID,
        number=number,
        from_location_id=origin.id,
        to_location_id=target.id,
        transfer_date=on,
        note=data.note,
        lines=[
            StockTransferLine(tenant_id=TENANT_ID, item_id=i, quantity=q) for i, q in wanted.items()
        ],
    )
    db.add(transfer)
    db.flush()
    for item_id, base_qty in wanted.items():
        # Both legs at the company-wide average, so a transfer never changes value (G6).
        cost = positions[item_id].avg_cost
        for place, direction in ((origin.id, "out"), (target.id, "in")):
            ledgers.add_stock_move(
                db,
                item_id=item_id,
                location_id=place,
                entry_date=on,
                qty_in=base_qty if direction == "in" else ZERO,
                qty_out=base_qty if direction == "out" else ZERO,
                unit_cost=cost,
                ref_type=StockRef.TRANSFER,
                ref_id=transfer.id,
                narration=f"Transfer {number}",
                actor_id=actor_id,
            )
    db.commit()
    return _transfer_view(db, transfer)


def list_transfers(db: Session, location_ids: frozenset[int] | None) -> list[TransferOut]:
    stmt = select(StockTransfer).where(StockTransfer.tenant_id == TENANT_ID)
    if location_ids is not None:
        stmt = stmt.where(
            StockTransfer.from_location_id.in_(location_ids)
            | StockTransfer.to_location_id.in_(location_ids)
        )
    rows = db.execute(
        stmt.order_by(StockTransfer.transfer_date.desc(), StockTransfer.id.desc()).limit(200)
    ).scalars()
    return [_transfer_view(db, t) for t in rows]


def get_transfer(db: Session, transfer_id: int) -> TransferOut:
    row = db.get(StockTransfer, transfer_id)
    if row is None or row.tenant_id != TENANT_ID:
        raise NotFoundError("Transfer not found")
    return _transfer_view(db, row)


# ---------------------------------------------------------------------------- counts


def _count_row(db: Session, count_id: int) -> StockCount:
    row = db.get(StockCount, count_id)
    if row is None or row.tenant_id != TENANT_ID:
        raise NotFoundError("Count not found")
    return row


def _avg_cost(db: Session, item_id: int) -> Decimal:
    return ledgers.stock_position(db, item_id)[0].avg_cost


def count_view(db: Session, row: StockCount, with_cost: bool) -> CountOut | CountOwnerOut:
    items = {i.id: i for i in db.execute(select(Item)).scalars()}
    location = db.get(Location, row.location_id)
    base = {
        "id": row.id,
        "location_id": row.location_id,
        "location_code": location.code if location else "",
        "count_date": row.count_date,
        "status": row.status,
        "note": row.note,
    }
    if not with_cost:
        return CountOut(
            **base,
            lines=[
                CountLineOut(
                    item_id=line.item_id,
                    item_name=items[line.item_id].name,
                    base_unit=items[line.item_id].base_unit,
                    system_qty=line.system_qty,
                    counted_qty=line.counted_qty,
                    variance=line.variance,
                )
                for line in row.lines
            ],
        )
    lines = []
    total = ZERO
    for line in row.lines:
        value = (
            money(line.variance * _avg_cost(db, line.item_id))
            if line.variance is not None
            else None
        )
        total += value or ZERO
        lines.append(
            CountLineOwnerOut(
                item_id=line.item_id,
                item_name=items[line.item_id].name,
                base_unit=items[line.item_id].base_unit,
                system_qty=line.system_qty,
                counted_qty=line.counted_qty,
                variance=line.variance,
                variance_value=value,
            )
        )
    return CountOwnerOut(**base, lines=lines, total_variance_value=money(total))


def open_count(db: Session, data: CountCreate, *, actor_id: int, can_access: bool) -> StockCount:
    if not can_access:
        raise PermissionDeniedError("You can only count your own shop")
    location = _location(db, data.location_id, "location_id")
    if data.item_ids is None:
        item_ids = sorted(
            {
                r
                for (r,) in db.execute(
                    select(StockLedger.item_id)
                    .where(
                        StockLedger.tenant_id == TENANT_ID, StockLedger.location_id == location.id
                    )
                    .distinct()
                )
            }
        )
    else:
        item_ids = sorted(set(data.item_ids))
    lines = []
    for item_id in item_ids:
        item = db.get(Item, item_id)
        if item is None or item.tenant_id != TENANT_ID:
            raise NotFoundError("Item not found", field="item_ids")
        _, here = ledgers.stock_position(db, item_id, location.id)
        lines.append(StockCountLine(tenant_id=TENANT_ID, item_id=item_id, system_qty=here))
    if not lines:
        raise BusinessRuleError(
            "Nothing has been stocked here yet. Pick the items to count.", code="NOTHING_TO_COUNT"
        )
    row = StockCount(
        tenant_id=TENANT_ID,
        location_id=location.id,
        count_date=data.count_date or today_ist(),
        status=CountStatus.DRAFT,
        note=data.note,
        lines=lines,
    )
    db.add(row)
    db.commit()
    return row


def get_count(db: Session, count_id: int) -> StockCount:
    return _count_row(db, count_id)


def list_counts(db: Session, location_ids: frozenset[int] | None) -> list[StockCount]:
    stmt = select(StockCount).where(StockCount.tenant_id == TENANT_ID)
    if location_ids is not None:
        stmt = stmt.where(StockCount.location_id.in_(location_ids))
    return list(db.execute(stmt.order_by(StockCount.id.desc()).limit(100)).scalars())


def enter_counts(db: Session, count_id: int, data: CountLinesUpdate) -> StockCount:
    row = _count_row(db, count_id)
    if row.status is CountStatus.POSTED:
        raise BusinessRuleError("This count is already posted", code="COUNT_POSTED")
    by_item = {line.item_id: line for line in row.lines}
    for entry in data.lines:
        line = by_item.get(entry.item_id)
        if line is None:
            raise NotFoundError("That item is not in this count", field="item_id")
        line.counted_qty = entry.counted_qty
    db.commit()
    return row


def post_count(db: Session, count_id: int, actor_id: int) -> StockCount:
    """Turn every counted line's variance into an adjustment at the average cost."""
    row = _count_row(db, count_id)
    if row.status is CountStatus.POSTED:
        raise BusinessRuleError("This count is already posted", code="COUNT_POSTED")
    counted = [line for line in row.lines if line.counted_qty is not None]
    if not counted:
        raise BusinessRuleError("Enter at least one counted quantity first", code="NOTHING_COUNTED")
    for line in counted:
        position, here = ledgers.stock_position(db, line.item_id, row.location_id)
        line.system_qty = here  # as the ledger stands now
        assert line.counted_qty is not None  # noqa: S101 - narrowed by the filter above
        line.variance = count_variance(here, line.counted_qty)
        if line.variance != ZERO:
            ledgers.add_stock_move(
                db,
                item_id=line.item_id,
                location_id=row.location_id,
                entry_date=row.count_date,
                qty_in=line.variance if line.variance > ZERO else ZERO,
                qty_out=-line.variance if line.variance < ZERO else ZERO,
                unit_cost=position.avg_cost,
                ref_type=StockRef.ADJUSTMENT,
                ref_id=row.id,
                narration=f"Stock count {row.id}",
                actor_id=actor_id,
            )
    row.status = CountStatus.POSTED
    row.posted_at = datetime.now(UTC)
    row.posted_by = actor_id
    db.commit()
    return row
