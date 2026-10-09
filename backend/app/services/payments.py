"""Supplier payments and advances (Milestone 4). Milestone 7 adds customer receipts."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.tenancy import TENANT_ID
from app.domain.money import ZERO
from app.models.enums import DocType, LedgerAccount, PartyRef, PartyType, PaymentDirection
from app.models.masters import Party
from app.models.purchasing import Payment
from app.models.setup import Location
from app.schemas.purchases import PaymentCreate, PaymentOut
from app.services import ledgers
from app.services.numbering import allocate_number
from app.services.shop_settings import get_settings_row


def _view(db: Session, payment: Payment) -> PaymentOut:
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
    )


def create_supplier_payment(
    db: Session, data: PaymentCreate, *, actor_id: int, idempotency_key: str | None
) -> tuple[PaymentOut, bool]:
    """Returns (payment, created). A repeated Idempotency-Key returns the first payment (G19)."""
    if data.direction is not PaymentDirection.PAID:
        raise BusinessRuleError(
            "Customer receipts arrive in a later release", code="NOT_AVAILABLE", field="direction"
        )
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
            return _view(db, existing), False

    party = db.get(Party, data.party_id)
    if party is None or party.tenant_id != TENANT_ID:
        raise NotFoundError("Party not found", field="party_id")
    if party.type is PartyType.CUSTOMER:
        raise BusinessRuleError(
            "This is a customer; payments here go to suppliers",
            code="WRONG_PARTY_TYPE",
            field="party_id",
        )
    location = db.get(Location, data.location_id)
    if location is None or location.tenant_id != TENANT_ID or not location.is_active:
        raise NotFoundError("Location not found or inactive", field="location_id")

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
        **data.model_dump(),
    )
    db.add(payment)
    db.flush()
    ledgers.add_party_entry(
        db,
        party_id=party.id,
        site_id=None,
        account=LedgerAccount.PAYABLE,
        entry_date=data.payment_date,
        ref_type=PartyRef.PAYMENT,
        ref_id=payment.id,
        doc_no=number,
        debit=data.amount,
        credit=ZERO,
        narration=f"Paid by {data.mode.value}" + (f" ({data.reference})" if data.reference else ""),
        actor_id=actor_id,
    )
    db.commit()
    return _view(db, payment), True


def list_payments(db: Session, party_id: int | None = None) -> list[PaymentOut]:
    stmt = select(Payment).where(Payment.tenant_id == TENANT_ID)
    if party_id is not None:
        stmt = stmt.where(Payment.party_id == party_id)
    rows = db.execute(
        stmt.order_by(Payment.payment_date.desc(), Payment.id.desc()).limit(200)
    ).scalars()
    return [_view(db, p) for p in rows]
