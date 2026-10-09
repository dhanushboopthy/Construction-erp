"""Money received from customers and paid to suppliers (Milestones 4 and 7).

A payment writes one or more credit (customer) or debit (supplier) rows on the party ledger.
Rows aimed at a bill carry its number in `applies_to`; the rest is applied oldest bill first
by the ledger maths, and anything beyond the bills stays as an advance (G21)."""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.tenancy import TENANT_ID
from app.domain import ledger as ledger_rules
from app.domain.compliance import cash_receipt_blocked
from app.domain.ledger import Account, LedgerEntry
from app.domain.money import ZERO, money
from app.models.enums import (
    DocType,
    LedgerAccount,
    PartyRef,
    PartyType,
    PaymentDirection,
    PaymentMode,
)
from app.models.ledgers import PartyLedger
from app.models.masters import Party, Site
from app.models.purchasing import Payment
from app.models.setup import Location
from app.schemas.ledger import OpenBillOut, OpenBillsOut
from app.schemas.purchases import AllocationIn, AllocationOut, PaymentCreate, PaymentOut
from app.services import ledgers
from app.services.numbering import allocate_number
from app.services.shop_settings import get_settings_row


def _account(direction: PaymentDirection) -> LedgerAccount:
    return (
        LedgerAccount.RECEIVABLE
        if direction is PaymentDirection.RECEIVED
        else LedgerAccount.PAYABLE
    )


def _open(db: Session, party_id: int, account: LedgerAccount) -> ledger_rules.OpenItems:
    rows = db.execute(
        select(PartyLedger)
        .where(
            PartyLedger.tenant_id == TENANT_ID,
            PartyLedger.party_id == party_id,
            PartyLedger.account == account,
        )
        .order_by(PartyLedger.entry_date, PartyLedger.id)
    ).scalars()
    entries = [
        LedgerEntry(r.entry_date, r.debit, r.credit, r.doc_no or "", r.applies_to) for r in rows
    ]
    return ledger_rules.open_items(entries, Account(account.value))


def cash_received_on(db: Session, party_id: int, on: date) -> Decimal:
    total = db.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.tenant_id == TENANT_ID,
            Payment.party_id == party_id,
            Payment.direction == PaymentDirection.RECEIVED,
            Payment.mode == PaymentMode.CASH,
            Payment.payment_date == on,
        )
    ).scalar_one()
    return money(total)


def check_cash_limit(db: Session, party_id: int, on: date, new_cash: Decimal) -> str | None:
    """Rule G14: cash of the limit or more from one person in a day is refused."""
    limit = get_settings_row(db).cash_receipt_limit
    if cash_receipt_blocked(cash_received_on(db, party_id, on), new_cash, limit):
        return (
            f"Cash of ₹{limit:,.0f} or more from one customer in a day is not allowed. "
            "Take the rest by UPI or bank transfer."
        )
    return None


def _view(
    db: Session, payment: Payment, applied: list[AllocationOut], advance: Decimal
) -> PaymentOut:
    party = db.get(Party, payment.party_id)
    return PaymentOut(
        id=payment.id,
        number=payment.number,
        direction=payment.direction,
        party_id=payment.party_id,
        party_name=party.name if party else "",
        location_id=payment.location_id,
        amount=payment.amount,
        mode=payment.mode,
        reference=payment.reference,
        payment_date=payment.payment_date,
        note=payment.note,
        site_id=payment.site_id,
        applied=applied,
        advance=advance,
    )


def _write(
    db: Session,
    payment: Payment,
    account: LedgerAccount,
    picks: list[AllocationIn],
    actor_id: int,
) -> None:
    """One ledger row per bill aimed at, then one for the rest (oldest first)."""
    debit_side = account is LedgerAccount.PAYABLE
    narration = f"{payment.mode.value.upper()}" + (
        f" {payment.reference}" if payment.reference else ""
    )
    left = payment.amount
    for pick in picks:
        ledgers.add_party_entry(
            db,
            party_id=payment.party_id,
            site_id=payment.site_id,
            account=account,
            entry_date=payment.payment_date,
            ref_type=PartyRef.PAYMENT,
            ref_id=payment.id,
            doc_no=payment.number,
            applies_to=pick.bill_no,
            debit=pick.amount if debit_side else ZERO,
            credit=ZERO if debit_side else pick.amount,
            narration=narration,
            actor_id=actor_id,
        )
        left -= pick.amount
    if left > ZERO:
        ledgers.add_party_entry(
            db,
            party_id=payment.party_id,
            site_id=payment.site_id,
            account=account,
            entry_date=payment.payment_date,
            ref_type=PartyRef.PAYMENT,
            ref_id=payment.id,
            doc_no=payment.number,
            debit=left if debit_side else ZERO,
            credit=ZERO if debit_side else left,
            narration=narration,
            actor_id=actor_id,
        )


def create_payment(
    db: Session,
    data: PaymentCreate,
    *,
    actor_id: int,
    is_owner: bool,
    can_access: bool,
    idempotency_key: str | None,
) -> tuple[PaymentOut, bool]:
    """Returns (payment, created). A repeated Idempotency-Key returns the first payment (G19)."""
    received = data.direction is PaymentDirection.RECEIVED
    if not received and not is_owner:
        raise PermissionDeniedError("Only the owner can pay suppliers")
    if not can_access:
        raise PermissionDeniedError("You can only record payments for your own shop")
    if idempotency_key:
        existing = db.execute(
            select(Payment).where(
                Payment.tenant_id == TENANT_ID, Payment.idempotency_key == idempotency_key
            )
        ).scalar_one_or_none()
        if existing:
            if existing.party_id != data.party_id or existing.amount != data.amount:
                raise ConflictError(
                    "This Idempotency-Key was used for a different payment",
                    code="IDEMPOTENCY_CONFLICT",
                )
            return _view(db, existing, [], ZERO), False

    party = db.get(Party, data.party_id)
    if party is None or party.tenant_id != TENANT_ID:
        raise NotFoundError("Party not found", field="party_id")
    wrong = party.type is (PartyType.SUPPLIER if received else PartyType.CUSTOMER)
    if wrong:
        raise BusinessRuleError(
            "This is a supplier; receipts are from customers"
            if received
            else "This is a customer; payments here go to suppliers",
            code="WRONG_PARTY_TYPE",
            field="party_id",
        )
    location = db.get(Location, data.location_id)
    if location is None or location.tenant_id != TENANT_ID or not location.is_active:
        raise NotFoundError("Location not found or inactive", field="location_id")
    if data.site_id is not None:
        site = db.get(Site, data.site_id)
        if not received or site is None or site.party_id != party.id:
            raise BusinessRuleError(
                "The site must belong to this customer", code="SITE_MISMATCH", field="site_id"
            )

    if received and data.mode is PaymentMode.CASH:
        message = check_cash_limit(db, party.id, data.payment_date, data.amount)
        if message:
            raise BusinessRuleError(message, code="CASH_LIMIT_REACHED", field="amount")

    account = _account(data.direction)
    opened = _open(db, party.id, account)
    picks = {p.bill_no: p.amount for p in data.allocations}
    if len(picks) != len(data.allocations):
        raise BusinessRuleError(
            "A bill is listed twice", code="ALLOCATION_INVALID", field="allocations"
        )
    try:
        allocation = ledger_rules.allocate(opened, data.amount, picks or None)
    except ValueError as exc:
        raise BusinessRuleError(str(exc), code="ALLOCATION_INVALID", field="allocations") from exc

    settings = get_settings_row(db)
    number = allocate_number(
        db,
        location_id=location.id,
        doc_type=DocType.PAYMENT_RECEIPT,
        on=data.payment_date,
        fy_start_month=settings.financial_year_start_month,
    )
    payment = Payment(
        tenant_id=TENANT_ID,
        number=number,
        idempotency_key=idempotency_key,
        **data.model_dump(exclude={"allocations"}),
    )
    db.add(payment)
    db.flush()
    _write(db, payment, account, data.allocations, actor_id)
    db.commit()
    applied = [AllocationOut(bill_no=ref, amount=amount) for ref, amount in allocation.applied]
    return _view(db, payment, applied, allocation.advance), True


def receive_at_billing(
    db: Session,
    *,
    party: Party,
    site_id: int | None,
    location_id: int,
    invoice_number: str,
    on: date,
    parts: list[tuple[PaymentMode, Decimal, str | None]],
    actor_id: int,
) -> list[Payment]:
    """Money taken at the counter with the bill: one receipt per mode, applied to that bill."""
    settings = get_settings_row(db)
    made: list[Payment] = []
    for mode, amount, reference in parts:
        number = allocate_number(
            db,
            location_id=location_id,
            doc_type=DocType.PAYMENT_RECEIPT,
            on=on,
            fy_start_month=settings.financial_year_start_month,
        )
        payment = Payment(
            tenant_id=TENANT_ID,
            number=number,
            direction=PaymentDirection.RECEIVED,
            party_id=party.id,
            site_id=site_id,
            location_id=location_id,
            amount=amount,
            mode=mode,
            reference=reference,
            payment_date=on,
            note=f"With bill {invoice_number}",
        )
        db.add(payment)
        db.flush()
        _write(
            db,
            payment,
            LedgerAccount.RECEIVABLE,
            [AllocationIn(bill_no=invoice_number, amount=amount)],
            actor_id,
        )
        made.append(payment)
    return made


def list_payments(
    db: Session, party_id: int | None, location_ids: frozenset[int] | None
) -> list[PaymentOut]:
    stmt = select(Payment).where(Payment.tenant_id == TENANT_ID)
    if party_id is not None:
        stmt = stmt.where(Payment.party_id == party_id)
    if location_ids is not None:
        # Counter staff see receipts of their own shop only, never what is paid to suppliers.
        stmt = stmt.where(
            Payment.location_id.in_(location_ids), Payment.direction == PaymentDirection.RECEIVED
        )
    rows = db.execute(
        stmt.order_by(Payment.payment_date.desc(), Payment.id.desc()).limit(200)
    ).scalars()
    return [_view(db, p, [], ZERO) for p in rows]


def open_bills_view(db: Session, party_id: int, account: LedgerAccount) -> OpenBillsOut:
    party = db.get(Party, party_id)
    if party is None or party.tenant_id != TENANT_ID:
        raise NotFoundError("Party not found")
    opened = _open(db, party_id, account)
    return OpenBillsOut(
        party_id=party_id,
        account=account,
        advance=opened.advance,
        bills=[
            OpenBillOut(
                bill_no=i.ref,
                bill_date=i.entry_date,
                due_date=None,
                original=i.original,
                remaining=i.remaining,
                overdue=False,
            )
            for i in opened.items
        ],
    )
