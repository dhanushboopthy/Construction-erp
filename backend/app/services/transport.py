"""Hired vehicles, trips and freight (Milestone 9, B18), and direct (drop-ship) links (B10)."""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import today_ist
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.tenancy import TENANT_ID
from app.domain import dropship
from app.domain.compliance import freight_cash_warning
from app.domain.money import ZERO, money
from app.models.enums import (
    FulfilmentSource,
    LedgerAccount,
    PartyRef,
    PartyType,
    PaymentDirection,
    PaymentMode,
    PurchaseMode,
)
from app.models.ledgers import PartyLedger
from app.models.masters import Item, Party
from app.models.purchasing import Payment, Purchase, PurchaseLine
from app.models.sales import SalesInvoice, SalesLine
from app.models.setup import Location
from app.models.transport import DropShipLink, Trip, Vehicle
from app.schemas.transport import (
    DropShipReport,
    DropShipRow,
    LinkCreate,
    OpenDirectLineOut,
    TripCreate,
    TripOut,
    VehicleCreate,
    VehicleUpdate,
)
from app.services import closing as closing_service
from app.services import ledgers
from app.services.shop_settings import get_settings_row

# G14: cash freight above this a day to one transporter is not deductible (accountant to confirm).
CASH_FREIGHT_DAILY_LIMIT = Decimal("35000")


def trip_ref(trip_id: int) -> str:
    return f"TRIP-{trip_id}"


# ---------------------------------------------------------------------------- vehicles


def create_vehicle(db: Session, data: VehicleCreate, *, actor_id: int) -> Vehicle:
    exists = db.execute(
        select(Vehicle.id).where(Vehicle.tenant_id == TENANT_ID, Vehicle.number == data.number)
    ).first()
    if exists:
        raise ConflictError("This vehicle number is already listed", code="VEHICLE_EXISTS")
    party_id: int | None = None
    if not data.is_own:
        # Freight is payable to the vehicle's owner, so each hired vehicle gets a supplier account.
        settings = get_settings_row(db)
        name = f"Transport: {data.owner_name} ({data.number})"
        taken = db.execute(
            select(Party.id).where(Party.tenant_id == TENANT_ID, Party.name == name)
        ).first()
        if taken:
            raise ConflictError("A supplier with this name already exists", code="PARTY_EXISTS")
        party = Party(
            tenant_id=TENANT_ID,
            name=name,
            type=PartyType.SUPPLIER,
            state_code=settings.state_code,
            address="",
            phone=data.phone,
            created_by=actor_id,
        )
        db.add(party)
        db.flush()
        party_id = party.id
    vehicle = Vehicle(
        tenant_id=TENANT_ID,
        number=data.number,
        owner_name=data.owner_name,
        phone=data.phone,
        is_own=data.is_own,
        party_id=party_id,
        created_by=actor_id,
    )
    db.add(vehicle)
    db.commit()
    return vehicle


def get_vehicle(db: Session, vehicle_id: int) -> Vehicle:
    row = db.get(Vehicle, vehicle_id)
    if row is None or row.tenant_id != TENANT_ID:
        raise NotFoundError("Vehicle not found")
    return row


def update_vehicle(db: Session, vehicle_id: int, data: VehicleUpdate, *, actor_id: int) -> Vehicle:
    vehicle = get_vehicle(db, vehicle_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        if value is not None or key == "phone":
            setattr(vehicle, key, value)
    vehicle.updated_by = actor_id
    db.commit()
    return vehicle


def list_vehicles(db: Session, include_inactive: bool) -> list[Vehicle]:
    stmt = select(Vehicle).where(Vehicle.tenant_id == TENANT_ID)
    if not include_inactive:
        stmt = stmt.where(Vehicle.is_active.is_(True))
    return list(db.execute(stmt.order_by(Vehicle.number)).scalars())


# ---------------------------------------------------------------------------- trips


def _paid(db: Session, vehicle: Vehicle, trip_id: int) -> Decimal:
    if vehicle.party_id is None:
        return ZERO
    total = db.execute(
        select(func.coalesce(func.sum(PartyLedger.debit), 0)).where(
            PartyLedger.tenant_id == TENANT_ID,
            PartyLedger.party_id == vehicle.party_id,
            PartyLedger.account == LedgerAccount.PAYABLE,
            PartyLedger.applies_to == trip_ref(trip_id),
        )
    ).scalar_one()
    return money(total)


def trip_view(db: Session, trip: Trip) -> TripOut:
    vehicle = get_vehicle(db, trip.vehicle_id)
    invoice = db.get(SalesInvoice, trip.invoice_id) if trip.invoice_id else None
    purchase = db.get(Purchase, trip.purchase_id) if trip.purchase_id else None
    owes = vehicle.party_id is not None and trip.freight_amount > ZERO
    return TripOut(
        id=trip.id,
        trip_date=trip.trip_date,
        vehicle_id=vehicle.id,
        vehicle_number=vehicle.number,
        owner_name=vehicle.owner_name,
        location_id=trip.location_id,
        invoice_id=trip.invoice_id,
        invoice_number=invoice.number if invoice else None,
        purchase_id=trip.purchase_id,
        purchase_number=purchase.number if purchase else None,
        from_place=trip.from_place,
        to_place=trip.to_place,
        freight_amount=trip.freight_amount,
        paid_amount=_paid(db, vehicle, trip.id),
        pay_ref=trip_ref(trip.id) if owes else None,
        note=trip.note,
    )


def create_trip(db: Session, data: TripCreate, *, actor_id: int) -> Trip:
    vehicle = get_vehicle(db, data.vehicle_id)
    if not vehicle.is_active:
        raise BusinessRuleError("This vehicle is switched off", code="VEHICLE_INACTIVE")
    location = db.get(Location, data.location_id)
    if location is None or location.tenant_id != TENANT_ID or not location.is_active:
        raise NotFoundError("Location not found or inactive", field="location_id")
    if data.invoice_id is not None and data.purchase_id is not None:
        raise BusinessRuleError(
            "A trip belongs to a sale or a purchase, not both", code="TRIP_ONE_DOCUMENT"
        )
    if data.invoice_id is not None:
        invoice = db.get(SalesInvoice, data.invoice_id)
        if invoice is None or invoice.tenant_id != TENANT_ID:
            raise NotFoundError("Invoice not found", field="invoice_id")
    if data.purchase_id is not None:
        purchase = db.get(Purchase, data.purchase_id)
        if purchase is None or purchase.tenant_id != TENANT_ID:
            raise NotFoundError("Purchase not found", field="purchase_id")
    if vehicle.is_own and data.freight_amount > ZERO:
        raise BusinessRuleError(
            "Our own vehicle has no freight to pay",
            code="OWN_VEHICLE_FREIGHT",
            field="freight_amount",
        )
    on = data.trip_date or today_ist()
    closing_service.ensure_day_open(db, location.id, on)
    trip = Trip(
        tenant_id=TENANT_ID,
        trip_date=on,
        vehicle_id=vehicle.id,
        location_id=location.id,
        invoice_id=data.invoice_id,
        purchase_id=data.purchase_id,
        from_place=data.from_place,
        to_place=data.to_place,
        freight_amount=data.freight_amount,
        note=data.note,
        created_by=actor_id,
    )
    db.add(trip)
    db.flush()
    if vehicle.party_id is not None and data.freight_amount > ZERO:
        ledgers.lock_party(db, vehicle.party_id)
        ledgers.add_party_entry(
            db,
            party_id=vehicle.party_id,
            site_id=None,
            account=LedgerAccount.PAYABLE,
            entry_date=on,
            ref_type=PartyRef.FREIGHT,
            ref_id=trip.id,
            doc_no=trip_ref(trip.id),
            credit=data.freight_amount,
            narration=f"Freight {vehicle.number}: {data.from_place} to {data.to_place}",
            actor_id=actor_id,
        )
    db.commit()
    return trip


def list_trips(
    db: Session, *, invoice_id: int | None, vehicle_id: int | None, limit: int, offset: int
) -> tuple[list[Trip], int]:
    filters = [Trip.tenant_id == TENANT_ID]
    if invoice_id is not None:
        filters.append(Trip.invoice_id == invoice_id)
    if vehicle_id is not None:
        filters.append(Trip.vehicle_id == vehicle_id)
    total = db.execute(select(func.count()).select_from(Trip).where(*filters)).scalar_one()
    rows = db.execute(
        select(Trip)
        .where(*filters)
        .order_by(Trip.trip_date.desc(), Trip.id.desc())
        .limit(limit)
        .offset(offset)
    ).scalars()
    return list(rows), total


def freight_cash_note(db: Session, party_id: int, on: date, new_cash: Decimal) -> str | None:
    """A warning (not a block) when cash paid to one person in a day passes the limit."""
    already = db.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.tenant_id == TENANT_ID,
            Payment.party_id == party_id,
            Payment.direction == PaymentDirection.PAID,
            Payment.mode == PaymentMode.CASH,
            Payment.payment_date == on,
        )
    ).scalar_one()
    if freight_cash_warning(money(already), new_cash, CASH_FREIGHT_DAILY_LIMIT):
        return (
            f"Cash of more than ₹{CASH_FREIGHT_DAILY_LIMIT:,.0f} a day to one person is not "
            "deductible as an expense. Consider UPI or bank transfer."
        )
    return None


# ---------------------------------------------------------------------------- direct links


def _linked(db: Session, purchase_line_id: int) -> list[Decimal]:
    return list(
        db.execute(
            select(DropShipLink.base_qty).where(DropShipLink.purchase_line_id == purchase_line_id)
        ).scalars()
    )


def free_qty(db: Session, line: PurchaseLine) -> Decimal:
    return dropship.remaining_to_link(line.billed_qty, _linked(db, line.id))


def open_direct_lines(db: Session, item_id: int | None) -> list[OpenDirectLineOut]:
    stmt = (
        select(PurchaseLine, Purchase)
        .join(Purchase, Purchase.id == PurchaseLine.purchase_id)
        .where(Purchase.tenant_id == TENANT_ID, Purchase.mode == PurchaseMode.DIRECT)
        .order_by(Purchase.bill_date.desc(), PurchaseLine.id)
    )
    if item_id is not None:
        stmt = stmt.where(PurchaseLine.item_id == item_id)
    out: list[OpenDirectLineOut] = []
    for line, purchase in db.execute(stmt).all():
        free = free_qty(db, line)
        if free <= ZERO:
            continue
        item = db.get(Item, line.item_id)
        supplier = db.get(Party, purchase.supplier_id)
        out.append(
            OpenDirectLineOut(
                purchase_line_id=line.id,
                purchase_number=purchase.number,
                supplier_name=supplier.name if supplier else "",
                bill_no=purchase.bill_no,
                bill_date=purchase.bill_date,
                item_id=line.item_id,
                item_name=item.name if item else "",
                free_qty=free,
                base_unit=item.base_unit if item else "",
            )
        )
    return out


def check_linkable(
    db: Session,
    purchase_line_id: int,
    item_id: int,
    base_qty: Decimal,
    *,
    also_taken: Decimal = ZERO,
) -> PurchaseLine:
    """Validate that a direct sale of `item_id` can draw `base_qty` from this purchase line."""
    line = db.get(PurchaseLine, purchase_line_id)
    purchase = db.get(Purchase, line.purchase_id) if line else None
    if line is None or purchase is None or purchase.tenant_id != TENANT_ID:
        raise NotFoundError("Purchase line not found", field="purchase_line_id")
    if purchase.mode is not PurchaseMode.DIRECT:
        raise BusinessRuleError(
            "Only a purchase entered as 'direct to customer' can supply a direct sale",
            code="LINK_NOT_DIRECT",
            field="purchase_line_id",
        )
    if line.item_id != item_id:
        raise BusinessRuleError(
            "That purchase line is a different item",
            code="LINK_WRONG_ITEM",
            field="purchase_line_id",
        )
    item = db.get(Item, item_id)
    try:
        dropship.check_link(
            line.billed_qty,
            [*_linked(db, line.id), also_taken],
            base_qty,
            item.base_unit if item else "",
        )
    except ValueError as exc:
        raise BusinessRuleError(str(exc), code="LINK_TOO_MUCH", field="purchase_line_id") from exc
    return line


def add_link(
    db: Session, sales_line: SalesLine, purchase_line: PurchaseLine, actor_id: int
) -> DropShipLink:
    link = DropShipLink(
        tenant_id=TENANT_ID,
        sales_line_id=sales_line.id,
        purchase_line_id=purchase_line.id,
        base_qty=sales_line.base_qty,
        unit_cost=purchase_line.unit_cost,
        created_by=actor_id,
    )
    db.add(link)
    return link


def link_after_billing(db: Session, data: LinkCreate, *, actor_id: int) -> DropShipLink:
    """Owner ties an already-saved direct sale line to the purchase that supplied it."""
    sales_line = db.get(SalesLine, data.sales_line_id)
    if sales_line is None or sales_line.tenant_id != TENANT_ID:
        raise NotFoundError("Sales line not found", field="sales_line_id")
    if sales_line.fulfilment_source is not FulfilmentSource.DIRECT:
        raise BusinessRuleError(
            "Only a line sent direct from the supplier can be linked",
            code="LINK_NOT_DIRECT_LINE",
            field="sales_line_id",
        )
    if db.execute(
        select(DropShipLink.id).where(DropShipLink.sales_line_id == sales_line.id)
    ).first():
        raise ConflictError("This sale line is already linked", code="LINK_EXISTS")
    ledgers.lock_items(db, {sales_line.item_id})
    purchase_line = check_linkable(
        db, data.purchase_line_id, sales_line.item_id, sales_line.base_qty
    )
    link = add_link(db, sales_line, purchase_line, actor_id)
    db.commit()
    return link


def link_for(db: Session, sales_line_id: int) -> DropShipLink | None:
    return db.execute(
        select(DropShipLink).where(DropShipLink.sales_line_id == sales_line_id)
    ).scalar_one_or_none()


def invoice_freight(db: Session, invoice_id: int) -> Decimal:
    total = db.execute(
        select(func.coalesce(func.sum(Trip.freight_amount), 0)).where(
            Trip.tenant_id == TENANT_ID, Trip.invoice_id == invoice_id
        )
    ).scalar_one()
    return money(total)


def report(db: Session) -> DropShipReport:
    lines = db.execute(
        select(SalesLine, SalesInvoice)
        .join(SalesInvoice, SalesInvoice.id == SalesLine.invoice_id)
        .where(
            SalesInvoice.tenant_id == TENANT_ID,
            SalesLine.fulfilment_source == FulfilmentSource.DIRECT,
        )
        .order_by(SalesInvoice.invoice_date.desc(), SalesLine.id)
    ).all()
    rows: list[DropShipRow] = []
    freight_used: set[int] = set()
    for line, invoice in lines:
        link = link_for(db, line.id)
        purchase_no = supplier_name = None
        goods: Decimal | None = None
        if link:
            pl = db.get(PurchaseLine, link.purchase_line_id)
            purchase = db.get(Purchase, pl.purchase_id) if pl else None
            supplier = db.get(Party, purchase.supplier_id) if purchase else None
            purchase_no = purchase.number if purchase else None
            supplier_name = supplier.name if supplier else None
            goods = money(link.base_qty * link.unit_cost)
        # An invoice's freight is shown once, on its first direct line.
        freight = ZERO if invoice.id in freight_used else invoice_freight(db, invoice.id)
        freight_used.add(invoice.id)
        rows.append(
            DropShipRow(
                invoice_id=invoice.id,
                invoice_number=invoice.number,
                invoice_date=invoice.invoice_date,
                customer=invoice.bill_to_name,
                sales_line_id=line.id,
                item_name=line.description,
                base_qty=line.base_qty,
                base_unit=line.base_unit,
                taxable=line.taxable,
                purchase_number=purchase_no,
                supplier_name=supplier_name,
                goods_cost=goods,
                freight=freight,
                profit=dropship.profit(line.taxable, line.base_qty, link.unit_cost, freight)
                if link
                else None,
            )
        )
    return DropShipReport(
        rows=rows,
        unlinked=sum(1 for r in rows if r.goods_cost is None),
        profit_total=money(sum((r.profit for r in rows if r.profit is not None), ZERO)),
    )
