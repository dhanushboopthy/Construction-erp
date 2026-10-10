"""Cement lots by manufacturing week (FM10, docs/FINANCE_REVIEW.md F25) — the smallest version.

A supplier delivery of cement may carry the manufacturing week printed on the bag (optional). A
sale of cement takes the oldest lot first and records which lots it took on the sale line. A
delivery with no week printed is ordered by the day it was received, so nothing is lost when the
week is not marked. Costing is unchanged: the company-wide average cost still prices every bag.

Layers are the shop's stock-mode deliveries of the item, less what was sent back by debit note and
less what earlier sales took. Opening stock, returns from customers and transfers in are not
layers: they count as stock the lots do not account for, which is older and goes first (see
`domain.orders.fifo_pick`)."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.tenancy import TENANT_ID
from app.domain import orders as rules
from app.domain.money import ZERO
from app.models.enums import ItemCategory, PurchaseMode
from app.models.masters import Item
from app.models.orders import SalesLineLot
from app.models.purchasing import Purchase, PurchaseLine
from app.models.returns import DebitNote, DebitNoteLine
from app.models.sales import SalesLine
from app.schemas.orders import LotOut
from app.services import ledgers


def tracks_lots(item: Item) -> bool:
    return item.category is ItemCategory.CEMENT


def _layers(db: Session, item_id: int, location_id: int) -> list[tuple[rules.Layer, PurchaseLine]]:
    rows = db.execute(
        select(PurchaseLine, Purchase.bill_date)
        .join(Purchase, Purchase.id == PurchaseLine.purchase_id)
        .where(
            Purchase.tenant_id == TENANT_ID,
            Purchase.location_id == location_id,
            Purchase.mode == PurchaseMode.STOCK,
            PurchaseLine.item_id == item_id,
        )
    ).all()
    if not rows:
        return []
    ids = [line.id for line, _ in rows]
    sent_back = dict(
        db.execute(
            select(DebitNoteLine.purchase_line_id, func.sum(DebitNoteLine.base_qty))
            .join(DebitNote, DebitNote.id == DebitNoteLine.debit_note_id)
            .where(DebitNoteLine.purchase_line_id.in_(ids))
            .group_by(DebitNoteLine.purchase_line_id)
        ).all()
    )
    taken = dict(
        db.execute(
            select(SalesLineLot.purchase_line_id, func.sum(SalesLineLot.base_qty))
            .where(SalesLineLot.purchase_line_id.in_(ids))
            .group_by(SalesLineLot.purchase_line_id)
        ).all()
    )
    out: list[tuple[rules.Layer, PurchaseLine]] = []
    for line, received_on in rows:
        left = line.received_qty - sent_back.get(line.id, ZERO) - taken.get(line.id, ZERO)
        if left <= ZERO:
            continue
        key = (
            rules.lot_date(line.mfg_year, line.mfg_week)
            if line.mfg_week is not None and line.mfg_year is not None
            else received_on
        )
        out.append((rules.Layer(line.id, key, left), line))
    return out


def record_picks(db: Session, sales_line: SalesLine, item: Item, location_id: int) -> None:
    """Take the oldest lots for a cement sale line and record them. Call before the sale's stock
    move is written, with the item locked, so the quantity on hand is what the sale started from."""
    if not tracks_lots(item):
        return
    layers = _layers(db, item.id, location_id)
    if not layers:
        return
    _, on_hand = ledgers.stock_position(db, item.id, location_id)
    by_id = {layer.id: purchase_line for layer, purchase_line in layers}
    picks = rules.fifo_pick([layer for layer, _ in layers], on_hand, sales_line.base_qty)
    for pick in picks:
        source = by_id[pick.layer_id]
        db.add(
            SalesLineLot(
                tenant_id=TENANT_ID,
                sales_line_id=sales_line.id,
                purchase_line_id=source.id,
                mfg_week=source.mfg_week,
                mfg_year=source.mfg_year,
                base_qty=pick.quantity,
            )
        )
    db.flush()


def lots_for_lines(db: Session, line_ids: list[int]) -> dict[int, list[LotOut]]:
    """The lots each sale line took, for the invoice screen."""
    if not line_ids:
        return {}
    rows = db.execute(
        select(SalesLineLot, Purchase.bill_date)
        .join(PurchaseLine, PurchaseLine.id == SalesLineLot.purchase_line_id)
        .join(Purchase, Purchase.id == PurchaseLine.purchase_id)
        .where(SalesLineLot.sales_line_id.in_(line_ids))
        .order_by(SalesLineLot.id)
    ).all()
    out: dict[int, list[LotOut]] = defaultdict(list)
    for lot, received_on in rows:
        out[lot.sales_line_id].append(
            LotOut(
                label=rules.lot_label(lot.mfg_week, lot.mfg_year, received_on),
                mfg_week=lot.mfg_week,
                mfg_year=lot.mfg_year,
                quantity=lot.base_qty,
            )
        )
    return dict(out)


def stock_by_lot(db: Session, item_id: int, location_id: int) -> list[tuple[str, date, Decimal]]:
    """What is left of each lot at a place, oldest first: (label, ordering date, quantity)."""
    out = []
    for layer, line in sorted(_layers(db, item_id, location_id), key=lambda x: (x[0].key, x[0].id)):
        purchase = db.get(Purchase, line.purchase_id)
        received_on = purchase.bill_date if purchase else layer.key
        out.append(
            (rules.lot_label(line.mfg_week, line.mfg_year, received_on), layer.key, layer.remaining)
        )
    return out
