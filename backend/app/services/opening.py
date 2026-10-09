"""Opening balances (Milestone 3): draft rows, then one posting that writes the ledgers."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.tenancy import TENANT_ID
from app.domain.money import ZERO
from app.models.enums import (
    LedgerAccount,
    OpeningKind,
    OpeningStatus,
    PartyRef,
    PartyType,
    StockRef,
)
from app.models.masters import Item, Party, Site
from app.models.opening import OpeningBalance
from app.models.setup import Location
from app.schemas.opening import MONEY_KINDS, OpeningCreate, OpeningOut, OpeningUpdate, PostResult
from app.services import ledgers

CUSTOMER_KINDS = {OpeningKind.RECEIVABLE, OpeningKind.CUSTOMER_ADVANCE}
SUPPLIER_KINDS = {OpeningKind.PAYABLE, OpeningKind.SUPPLIER_ADVANCE}


def _get(db: Session, row_id: int) -> OpeningBalance:
    row = db.get(OpeningBalance, row_id)
    if row is None or row.tenant_id != TENANT_ID:
        raise NotFoundError("Opening entry not found")
    return row


def _require_draft(row: OpeningBalance) -> None:
    if row.status is OpeningStatus.POSTED:
        raise BusinessRuleError(
            "This entry is already posted to the ledger and is locked. Correct it with a stock "
            "count or a credit or debit note.",
            code="OPENING_POSTED",
        )


def _validate_refs(
    db: Session,
    kind: OpeningKind,
    *,
    item_id: int | None,
    location_id: int | None,
    party_id: int | None,
    site_id: int | None,
) -> None:
    if kind is OpeningKind.STOCK:
        item = db.get(Item, item_id) if item_id else None
        if item is None or item.tenant_id != TENANT_ID or not item.is_active:
            raise NotFoundError("Item not found or inactive", field="item_id")
        location = db.get(Location, location_id) if location_id else None
        if location is None or location.tenant_id != TENANT_ID or not location.is_active:
            raise NotFoundError("Location not found or inactive", field="location_id")
        return
    party = db.get(Party, party_id) if party_id else None
    if party is None or party.tenant_id != TENANT_ID:
        raise NotFoundError("Party not found", field="party_id")
    wants_customer = kind in CUSTOMER_KINDS
    if wants_customer and party.type is PartyType.SUPPLIER:
        raise BusinessRuleError(
            "This is a supplier; use a payable or supplier advance",
            code="WRONG_PARTY_TYPE",
            field="party_id",
        )
    if not wants_customer and party.type is PartyType.CUSTOMER:
        raise BusinessRuleError(
            "This is a customer; use a receivable or customer advance",
            code="WRONG_PARTY_TYPE",
            field="party_id",
        )
    if site_id is not None:
        site = db.get(Site, site_id)
        if not wants_customer or site is None or site.party_id != party.id:
            raise BusinessRuleError(
                "The site must belong to this customer", code="SITE_MISMATCH", field="site_id"
            )


def _flush(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            "An opening figure for this item and location, or this party, site and kind, "
            "already exists. Edit it instead.",
            code="OPENING_EXISTS",
        ) from exc


def create_row(db: Session, data: OpeningCreate) -> OpeningBalance:
    _validate_refs(
        db,
        data.kind,
        item_id=data.item_id,
        location_id=data.location_id,
        party_id=data.party_id,
        site_id=data.site_id,
    )
    row = OpeningBalance(tenant_id=TENANT_ID, status=OpeningStatus.DRAFT, **data.model_dump())
    db.add(row)
    _flush(db)
    db.commit()
    return row


def update_row(db: Session, row_id: int, data: OpeningUpdate) -> OpeningBalance:
    row = _get(db, row_id)
    _require_draft(row)
    changes = data.model_dump(exclude_unset=True)
    stock = row.kind is OpeningKind.STOCK
    for key in ("location_id", "quantity", "unit_cost"):
        if key in changes and not stock:
            raise BusinessRuleError(
                f"{key} applies to opening stock only", code="WRONG_FIELD", field=key
            )
    for key in ("site_id", "amount"):
        if key in changes and stock:
            raise BusinessRuleError(
                f"{key} applies to balances only", code="WRONG_FIELD", field=key
            )
    _validate_refs(
        db,
        row.kind,
        item_id=row.item_id,
        location_id=changes.get("location_id", row.location_id),
        party_id=row.party_id,
        site_id=changes.get("site_id", row.site_id),
    )
    for key, value in changes.items():
        setattr(row, key, value)
    _flush(db)
    db.commit()
    return row


def delete_row(db: Session, row_id: int) -> None:
    """Drafts are working notes, not issued documents, so they can be removed."""
    row = _get(db, row_id)
    _require_draft(row)
    db.delete(row)
    db.commit()


def list_rows(
    db: Session, *, kind: OpeningKind | None = None, status: OpeningStatus | None = None
) -> list[OpeningOut]:
    stmt = select(OpeningBalance).where(OpeningBalance.tenant_id == TENANT_ID)
    if kind:
        stmt = stmt.where(OpeningBalance.kind == kind)
    if status:
        stmt = stmt.where(OpeningBalance.status == status)
    rows = list(db.execute(stmt.order_by(OpeningBalance.id)).scalars())

    items = {i.id: i for i in db.execute(select(Item)).scalars()}
    locations = {loc.id: loc for loc in db.execute(select(Location)).scalars()}
    parties = {p.id: p for p in db.execute(select(Party)).scalars()}
    sites = {s.id: s for s in db.execute(select(Site)).scalars()}
    out: list[OpeningOut] = []
    for r in rows:
        view = OpeningOut.model_validate(r)
        if r.item_id:
            view.item_name, view.base_unit = items[r.item_id].name, items[r.item_id].base_unit
        if r.location_id:
            view.location_code = locations[r.location_id].code
        if r.party_id:
            view.party_name = parties[r.party_id].name
        if r.site_id:
            view.site_name = sites[r.site_id].name
        out.append(view)
    return out


def get_view(db: Session, row_id: int) -> OpeningOut:
    row = _get(db, row_id)
    return next(v for v in list_rows(db) if v.id == row.id)


def post(db: Session, kinds: list[OpeningKind], actor_id: int) -> PostResult:
    """Write every draft of the chosen kinds to the ledgers in one transaction."""
    drafts = list(
        db.execute(
            select(OpeningBalance)
            .where(
                OpeningBalance.tenant_id == TENANT_ID,
                OpeningBalance.status == OpeningStatus.DRAFT,
                OpeningBalance.kind.in_(kinds),
            )
            .order_by(OpeningBalance.id)
        ).scalars()
    )
    if not drafts:
        raise BusinessRuleError("There is nothing to post for these types", code="NOTHING_TO_POST")
    now = datetime.now(UTC)
    stock_rows = party_rows = 0
    for row in drafts:
        if row.kind is OpeningKind.STOCK:
            if (
                row.item_id is None
                or row.location_id is None
                or row.quantity is None
                or row.unit_cost is None
            ):
                raise BusinessRuleError(
                    "Incomplete stock row", code="INCOMPLETE"
                )  # pragma: no cover
            ledgers.add_stock_move(
                db,
                item_id=row.item_id,
                location_id=row.location_id,
                entry_date=row.as_of,
                qty_in=row.quantity,
                unit_cost=row.unit_cost,
                ref_type=StockRef.OPENING,
                ref_id=row.id,
                narration=row.note or "Opening stock",
                actor_id=actor_id,
            )
            stock_rows += 1
        else:
            if row.party_id is None or row.amount is None:
                raise BusinessRuleError(
                    "Incomplete balance row", code="INCOMPLETE"
                )  # pragma: no cover
            account = (
                LedgerAccount.RECEIVABLE if row.kind in CUSTOMER_KINDS else LedgerAccount.PAYABLE
            )
            # Receivable: a due is a debit, an advance a credit. Payable: a due is a credit,
            # an advance paid to the supplier is a debit.
            is_due = row.kind in (OpeningKind.RECEIVABLE, OpeningKind.PAYABLE)
            debit_side = (account is LedgerAccount.RECEIVABLE) == is_due
            ledgers.add_party_entry(
                db,
                party_id=row.party_id,
                site_id=row.site_id,
                account=account,
                entry_date=row.as_of,
                ref_type=PartyRef.OPENING,
                ref_id=row.id,
                doc_no="Opening",
                debit=row.amount if debit_side else ZERO,
                credit=ZERO if debit_side else row.amount,
                narration=row.note or "Opening balance",
                actor_id=actor_id,
            )
            party_rows += 1
        row.status = OpeningStatus.POSTED
        row.posted_at = now
        row.posted_by = actor_id
    db.commit()
    return PostResult(posted=len(drafts), stock_rows=stock_rows, party_rows=party_rows)


__all__ = ["MONEY_KINDS", "create_row", "delete_row", "get_view", "list_rows", "post", "update_row"]
