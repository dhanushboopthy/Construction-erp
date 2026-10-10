"""Supplier target schemes (Milestone 11, B15). Progress is worked out from purchases and
returns every time, so it can never drift. Booking the rebate is the owner's decision (an
accountant should confirm the GST treatment, see GAP_ANALYSIS G29) and is done once."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import today_ist
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.tenancy import TENANT_ID
from app.domain import schemes as rules
from app.domain.money import ZERO, money
from app.models.enums import LedgerAccount, PartyRef, PartyType
from app.models.masters import Item, Party
from app.models.purchasing import Purchase, PurchaseLine
from app.models.returns import DebitNote, DebitNoteLine
from app.models.schemes import SupplierScheme
from app.schemas.schemes import SchemeCreate, SchemeOut, SchemeUpdate
from app.services import closing as closing_service
from app.services import ledgers


def _scheme(db: Session, scheme_id: int) -> SupplierScheme:
    row = db.get(SupplierScheme, scheme_id)
    if row is None or row.tenant_id != TENANT_ID:
        raise NotFoundError("Scheme not found")
    return row


def create(db: Session, data: SchemeCreate, *, actor_id: int) -> SupplierScheme:
    party = db.get(Party, data.party_id)
    if party is None or party.tenant_id != TENANT_ID or party.type is PartyType.CUSTOMER:
        raise NotFoundError("Supplier not found", field="party_id")
    unit = data.unit or ""  # the schema guarantees one for a category scheme
    if data.item_id is not None:
        item = db.get(Item, data.item_id)
        if item is None or item.tenant_id != TENANT_ID:
            raise NotFoundError("Item not found", field="item_id")
        unit = item.base_unit
    row = SupplierScheme(
        tenant_id=TENANT_ID,
        party_id=party.id,
        name=data.name,
        item_id=data.item_id,
        category=data.category,
        unit=unit,
        target_qty=data.target_qty,
        period_start=data.period_start,
        period_end=data.period_end,
        rebate_rule=data.rebate_rule,
        rebate_value=data.rebate_value,
        created_by=actor_id,
    )
    db.add(row)
    db.commit()
    return row


def update(db: Session, scheme_id: int, data: SchemeUpdate, *, actor_id: int) -> SupplierScheme:
    row = _scheme(db, scheme_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(row, key, value)
    row.updated_by = actor_id
    db.commit()
    return row


def _bought(db: Session, scheme: SupplierScheme) -> tuple[Decimal, Decimal]:
    """(base quantity, goods value) bought from the supplier in the period, less what went back."""
    match = [
        Purchase.tenant_id == TENANT_ID,
        Purchase.supplier_id == scheme.party_id,
        Purchase.bill_date >= scheme.period_start,
        Purchase.bill_date <= scheme.period_end,
    ]
    if scheme.item_id is not None:
        match.append(PurchaseLine.item_id == scheme.item_id)
    else:
        match.append(
            PurchaseLine.item_id.in_(
                select(Item.id).where(
                    Item.category == scheme.category, Item.base_unit == scheme.unit
                )
            )
        )
    got, value = db.execute(
        select(
            func.coalesce(func.sum(PurchaseLine.billed_qty), 0),
            func.coalesce(func.sum(PurchaseLine.goods_value), 0),
        )
        .join(Purchase, Purchase.id == PurchaseLine.purchase_id)
        .where(*match)
    ).one()
    back_qty, back_value = db.execute(
        select(
            func.coalesce(func.sum(DebitNoteLine.base_qty), 0),
            func.coalesce(func.sum(DebitNoteLine.taxable), 0),
        )
        .join(DebitNote, DebitNote.id == DebitNoteLine.debit_note_id)
        .join(PurchaseLine, PurchaseLine.id == DebitNoteLine.purchase_line_id)
        .join(Purchase, Purchase.id == PurchaseLine.purchase_id)
        .where(*match)
    ).one()
    return Decimal(got) - Decimal(back_qty), Decimal(value) - Decimal(back_value)


def view(db: Session, scheme: SupplierScheme) -> SchemeOut:
    achieved, value = _bought(db, scheme)
    p = rules.progress(scheme.target_qty, max(achieved, ZERO))
    party = db.get(Party, scheme.party_id)
    item = db.get(Item, scheme.item_id) if scheme.item_id else None
    return SchemeOut(
        id=scheme.id,
        party_id=scheme.party_id,
        party_name=party.name if party else "",
        name=scheme.name,
        item_id=scheme.item_id,
        item_name=item.name if item else None,
        category=scheme.category,
        unit=scheme.unit,
        target_qty=scheme.target_qty,
        period_start=scheme.period_start,
        period_end=scheme.period_end,
        rebate_rule=scheme.rebate_rule,
        rebate_value=scheme.rebate_value,
        is_active=scheme.is_active,
        achieved=p.achieved,
        pct=p.pct,
        remaining=p.remaining,
        reached=p.reached,
        alert=p.alert and scheme.is_active,
        projected_rebate=rules.rebate_amount(
            scheme.rebate_rule, scheme.rebate_value, max(value, ZERO), max(achieved, ZERO)
        ),
        rebate_amount=scheme.rebate_amount,
        rebate_booked_at=scheme.rebate_booked_at,
    )


def list_schemes(db: Session, *, party_id: int | None, alerts_only: bool) -> list[SchemeOut]:
    stmt = select(SupplierScheme).where(SupplierScheme.tenant_id == TENANT_ID)
    if party_id is not None:
        stmt = stmt.where(SupplierScheme.party_id == party_id)
    rows = db.execute(stmt.order_by(SupplierScheme.period_end.desc(), SupplierScheme.id)).scalars()
    views = [view(db, r) for r in rows]
    return [v for v in views if v.alert] if alerts_only else views


def book_rebate(db: Session, scheme_id: int, *, actor_id: int) -> SupplierScheme:
    scheme = _scheme(db, scheme_id)
    ledgers.lock_party(db, scheme.party_id)
    if scheme.rebate_booked_at is not None:
        raise ConflictError("The rebate for this scheme is already booked", code="REBATE_BOOKED")
    achieved, value = _bought(db, scheme)
    p = rules.progress(scheme.target_qty, max(achieved, ZERO))
    if not p.reached:
        raise BusinessRuleError(
            f"The target is not met yet: {p.pct}% done, {p.remaining.normalize():f} "
            f"{scheme.unit} to go",
            code="TARGET_NOT_MET",
        )
    amount = rules.rebate_amount(
        scheme.rebate_rule, scheme.rebate_value, max(value, ZERO), max(achieved, ZERO)
    )
    if amount <= ZERO:
        raise BusinessRuleError("The rebate works out to nothing", code="REBATE_ZERO")
    today = today_ist()
    closing_service.ensure_period_open(db, today)  # FM7: booking a rebate is a dated entry
    ledgers.add_party_entry(
        db,
        party_id=scheme.party_id,
        site_id=None,
        account=LedgerAccount.PAYABLE,
        entry_date=today,
        ref_type=PartyRef.REBATE,
        ref_id=scheme.id,
        doc_no=f"RB-{scheme.id}",
        debit=amount,
        narration=f"Rebate: {scheme.name}",
        actor_id=actor_id,
    )
    scheme.rebate_amount = money(amount)
    scheme.rebate_booked_at = datetime.now(UTC)
    scheme.updated_by = actor_id
    db.commit()
    return scheme
