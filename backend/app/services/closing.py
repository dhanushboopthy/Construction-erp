"""Daily closing per shop (Milestone 12, B12 and G17): the day's figures, the cash count, a PDF
saved date-wise to storage, and a lock on that shop-day's documents until the owner reopens it."""

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from weasyprint import HTML

from app.core.clock import today_ist
from app.core.config import StorageProvider, get_settings
from app.core.errors import (
    AppError,
    BusinessRuleError,
    ConflictError,
    NotFoundError,
)
from app.core.tenancy import TENANT_ID
from app.domain import closing as rules
from app.domain import controls as control_rules
from app.domain.money import ZERO, money
from app.models.documents import DailyClosing
from app.models.enums import (
    AuditAction,
    ClosingStatus,
    PaymentDirection,
    PaymentMode,
)
from app.models.purchasing import Payment, Purchase
from app.models.returns import CreditNote
from app.models.sales import SalesInvoice, SalesLine
from app.models.setup import AppUser, Location
from app.schemas.closing import (
    ClosingCreate,
    ClosingFigures,
    ClosingOut,
    ClosingPreview,
    ModeTotals,
    ReopenIn,
    TopItem,
)
from app.services.audit import record_event
from app.services.invoice_pdf import TEMPLATES, inr
from app.services.shop_settings import get_settings_row
from app.services.storage import StorageError, get_storage

TOP_ITEMS = 10


# ---------------------------------------------------------------------------- the day lock


def is_day_closed(db: Session, location_id: int, on: date) -> bool:
    return (
        db.execute(
            select(DailyClosing.id).where(
                DailyClosing.tenant_id == TENANT_ID,
                DailyClosing.location_id == location_id,
                DailyClosing.closing_date == on,
                DailyClosing.status == ClosingStatus.CLOSED,
            )
        ).first()
        is not None
    )


def ensure_period_open(db: Session, on: date) -> None:
    """Refuse a document dated on or before the books' lock date (FM7, F18). The lock is the
    owner's, set after a return is filed; a document dated inside it would put the books out of
    step with that return."""
    locked = get_settings_row(db).locked_through
    if control_rules.is_locked(on, locked) and locked is not None:
        raise BusinessRuleError(
            f"The books up to {locked:%d-%m-%Y} are locked, so nothing can be dated "
            f"{on:%d-%m-%Y}. Ask the owner to reopen them.",
            code="PERIOD_LOCKED",
        )


def ensure_day_open(db: Session, location_id: int, on: date) -> None:
    """Refuse a document dated on a locked period (FM7) or on a closed shop-day (G17). The owner
    can reopen either."""
    ensure_period_open(db, on)
    if is_day_closed(db, location_id, on):
        place = db.get(Location, location_id)
        raise BusinessRuleError(
            f"The books for {place.code if place else 'this shop'} on {on:%d-%m-%Y} are closed. "
            "Ask the owner to reopen the day.",
            code="DAY_CLOSED",
        )


# ---------------------------------------------------------------------------- the figures


def _sum(value: object) -> Decimal:
    return money(Decimal(str(value or 0)))


def figures(db: Session, location_id: int, on: date) -> ClosingFigures:
    place = db.get(Location, location_id)
    if place is None or place.tenant_id != TENANT_ID:
        raise NotFoundError("Shop not found", field="location_id")
    inv = [
        SalesInvoice.tenant_id == TENANT_ID,
        SalesInvoice.location_id == location_id,
        SalesInvoice.invoice_date == on,
    ]
    count, taxable, cgst, sgst, igst, rnd, total, unpaid = db.execute(
        select(
            func.count(),
            func.coalesce(func.sum(SalesInvoice.taxable_value), 0),
            func.coalesce(func.sum(SalesInvoice.cgst), 0),
            func.coalesce(func.sum(SalesInvoice.sgst), 0),
            func.coalesce(func.sum(SalesInvoice.igst), 0),
            func.coalesce(func.sum(SalesInvoice.round_off), 0),
            func.coalesce(func.sum(SalesInvoice.grand_total), 0),
            func.coalesce(func.sum(SalesInvoice.grand_total - SalesInvoice.paid_at_billing), 0),
        ).where(*inv)
    ).one()
    first = db.execute(
        select(SalesInvoice.number).where(*inv).order_by(SalesInvoice.id).limit(1)
    ).scalar()
    last = db.execute(
        select(SalesInvoice.number).where(*inv).order_by(SalesInvoice.id.desc()).limit(1)
    ).scalar()
    returns_count, returns_total = db.execute(
        select(func.count(), func.coalesce(func.sum(CreditNote.grand_total), 0)).where(
            CreditNote.tenant_id == TENANT_ID,
            CreditNote.location_id == location_id,
            CreditNote.note_date == on,
        )
    ).one()

    def received(mode: PaymentMode) -> Decimal:
        return _sum(
            db.execute(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.tenant_id == TENANT_ID,
                    Payment.location_id == location_id,
                    Payment.payment_date == on,
                    Payment.direction == PaymentDirection.RECEIVED,
                    Payment.mode == mode,
                )
            ).scalar_one()
        )

    cash, upi, bank = (
        received(PaymentMode.CASH),
        received(PaymentMode.UPI),
        received(PaymentMode.BANK),
    )
    cash_out = _sum(
        db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.tenant_id == TENANT_ID,
                Payment.location_id == location_id,
                Payment.payment_date == on,
                Payment.direction == PaymentDirection.PAID,
                Payment.mode == PaymentMode.CASH,
            )
        ).scalar_one()
    )
    from app.services.cashbook import drawer_moves

    moves = drawer_moves(db, location_id, on)
    purchases = db.execute(
        select(func.count())
        .select_from(Purchase)
        .where(
            Purchase.tenant_id == TENANT_ID,
            Purchase.location_id == location_id,
            Purchase.bill_date == on,
        )
    ).scalar_one()
    top = db.execute(
        select(
            SalesLine.description,
            SalesLine.base_unit,
            func.sum(SalesLine.base_qty),
            func.sum(SalesLine.taxable),
        )
        .join(SalesInvoice, SalesInvoice.id == SalesLine.invoice_id)
        .where(*inv)
        .group_by(SalesLine.description, SalesLine.base_unit)
        .order_by(func.sum(SalesLine.taxable).desc(), SalesLine.description)
        .limit(TOP_ITEMS)
    ).all()
    return ClosingFigures(
        location_id=place.id,
        location_code=place.code,
        closing_date=on,
        invoices_count=count,
        first_invoice=first,
        last_invoice=last,
        taxable=_sum(taxable),
        cgst=_sum(cgst),
        sgst=_sum(sgst),
        igst=_sum(igst),
        round_off=_sum(rnd),
        sales_total=_sum(total),
        credit_given=_sum(unpaid),
        returns_count=returns_count,
        returns_total=_sum(returns_total),
        receipts=ModeTotals(cash=cash, upi=upi, bank=bank, total=cash + upi + bank),
        paid_to_parties=cash_out,
        cash_expenses=moves.expenses,
        bank_deposits=moves.deposited,
        bank_withdrawals=moves.withdrawn,
        owner_drawings=moves.drawings,
        owner_capital=moves.capital,
        cash_in=money(cash + moves.cash_in),
        cash_out=money(cash_out + moves.cash_out),
        purchases_count=purchases,
        top_items=[
            TopItem(description=d, base_unit=u, quantity=Decimal(q), taxable=_sum(t))
            for d, u, q, t in top
        ],
    )


def _previous_counted(db: Session, location_id: int, before: date) -> Decimal:
    row = db.execute(
        select(DailyClosing.counted_cash)
        .where(
            DailyClosing.tenant_id == TENANT_ID,
            DailyClosing.location_id == location_id,
            DailyClosing.closing_date < before,
        )
        .order_by(DailyClosing.closing_date.desc())
        .limit(1)
    ).scalar()
    return money(row if row is not None else ZERO)


def _existing(db: Session, location_id: int, on: date) -> DailyClosing | None:
    return db.execute(
        select(DailyClosing).where(
            DailyClosing.tenant_id == TENANT_ID,
            DailyClosing.location_id == location_id,
            DailyClosing.closing_date == on,
        )
    ).scalar_one_or_none()


def view(db: Session, row: DailyClosing) -> ClosingOut:
    place = db.get(Location, row.location_id)
    return ClosingOut(
        id=row.id,
        location_id=row.location_id,
        location_code=place.code if place else "",
        closing_date=row.closing_date,
        status=row.status,
        invoices_count=row.invoices_count,
        sales_total=row.sales_total,
        returns_total=row.returns_total,
        opening_cash=row.opening_cash,
        cash_in=row.cash_in,
        cash_out=row.cash_out,
        expected_cash=row.expected_cash,
        counted_cash=row.counted_cash,
        difference=row.difference,
        note=row.note,
        closed_at=row.closed_at,
        reopened_at=row.reopened_at,
        reopen_reason=row.reopen_reason,
        times_closed=row.times_closed,
        has_pdf=row.pdf_key is not None,
    )


def preview(
    db: Session,
    location_id: int,
    on: date,
    *,
    can_access: Callable[[int], bool],
    profit: Callable[[int, date], Decimal] | None,
) -> ClosingPreview:
    if not can_access(location_id):
        raise NotFoundError("Shop not found", field="location_id")
    fig = figures(db, location_id, on)
    existing = _existing(db, location_id, on)
    opening = existing.opening_cash if existing else _previous_counted(db, location_id, on)
    return ClosingPreview(
        figures=fig,
        opening_cash=opening,
        expected_cash=rules.expected_cash(opening, fig.cash_in, fig.cash_out),
        existing=view(db, existing) if existing else None,
        locked=bool(existing and existing.status is ClosingStatus.CLOSED),
        profit=profit(location_id, on) if profit else None,
    )


# ---------------------------------------------------------------------------- close and reopen


def pdf_key(location_code: str, on: date) -> str:
    return f"closing/{location_code}/{on.year:04d}/{on.month:02d}/{on.isoformat()}.pdf"


def render_pdf(db: Session, fig: ClosingFigures, row: DailyClosing, closer: str) -> bytes:
    settings = get_settings_row(db)
    place = db.get(Location, row.location_id)
    env = Environment(
        loader=FileSystemLoader(Path(TEMPLATES)), autoescape=select_autoescape(["html"])
    )
    money_text = {
        "taxable": inr(fig.taxable),
        "cgst": inr(fig.cgst),
        "sgst": inr(fig.sgst),
        "igst": inr(fig.igst),
        "round_off": inr(fig.round_off),
        "sales_total": inr(fig.sales_total),
        "credit_given": inr(fig.credit_given),
        "returns_total": inr(fig.returns_total),
        "receipts_cash": inr(fig.receipts.cash),
        "receipts_upi": inr(fig.receipts.upi),
        "receipts_bank": inr(fig.receipts.bank),
        "receipts_total": inr(fig.receipts.total),
        "opening_cash": inr(row.opening_cash),
        "cash_in": inr(row.cash_in),
        "cash_out": inr(row.cash_out),
        "paid_to_parties": inr(fig.paid_to_parties),
        "cash_expenses": inr(fig.cash_expenses),
        "bank_deposits": inr(fig.bank_deposits),
        "bank_withdrawals": inr(fig.bank_withdrawals),
        "owner_drawings": inr(fig.owner_drawings),
        "owner_capital": inr(fig.owner_capital),
        "expected_cash": inr(row.expected_cash),
        "counted_cash": inr(row.counted_cash),
        "difference": inr(row.difference),
    }
    html = env.get_template("closing_a4.html").render(
        f=fig,
        m=money_text,
        seller={"legal_name": settings.legal_name, "trade_name": settings.trade_name},
        location_name=place.name if place else "",
        closed_at=(row.closed_at or datetime.now(UTC)).strftime("%d-%m-%Y %H:%M"),
        closed_by=closer,
        times_closed=row.times_closed,
        note=row.note,
        items=[
            {
                "description": i.description,
                "base_unit": i.base_unit,
                "qty": f"{i.quantity:f}".rstrip("0").rstrip("."),
                "taxable": inr(i.taxable),
            }
            for i in fig.top_items
        ],
        test_mark=not get_settings().is_production,
    )
    return HTML(string=html).write_pdf()  # type: ignore[no-any-return]


def close_day(
    db: Session,
    data: ClosingCreate,
    *,
    actor_id: int,
    can_access: Callable[[int], bool],
) -> DailyClosing:
    if not can_access(data.location_id):
        raise NotFoundError("Shop not found", field="location_id")
    if data.closing_date > today_ist():
        raise BusinessRuleError(
            "A day cannot be closed before it has happened",
            code="FUTURE_DATE",
            field="closing_date",
        )
    # One closing at a time per shop: stops two people closing the same day together.
    db.execute(select(func.pg_advisory_xact_lock(5, data.location_id)))
    existing = _existing(db, data.location_id, data.closing_date)
    if existing is not None and existing.status is ClosingStatus.CLOSED:
        raise ConflictError("This day is already closed", code="ALREADY_CLOSED")
    fig = figures(db, data.location_id, data.closing_date)
    opening = (
        data.opening_cash
        if data.opening_cash is not None
        else (
            existing.opening_cash
            if existing
            else _previous_counted(db, data.location_id, data.closing_date)
        )
    )
    expected = rules.expected_cash(opening, fig.cash_in, fig.cash_out)
    difference = rules.cash_difference(data.counted_cash, expected)
    note = (data.note or "").strip() or None
    if rules.note_needed(difference) and note is None:
        raise BusinessRuleError(
            f"The drawer is {'short' if difference < ZERO else 'over'} by ₹{abs(difference):,.2f}. "
            "Write a note before closing the day.",
            code="CASH_NOTE_REQUIRED",
            field="note",
        )
    now = datetime.now(UTC)
    row = existing or DailyClosing(
        tenant_id=TENANT_ID,
        location_id=data.location_id,
        closing_date=data.closing_date,
        times_closed=0,
        created_by=actor_id,
    )
    row.status = ClosingStatus.CLOSED
    row.invoices_count = fig.invoices_count
    row.sales_total = fig.sales_total
    row.returns_total = fig.returns_total
    row.opening_cash = opening
    row.cash_in = fig.cash_in
    row.cash_out = fig.cash_out
    row.expected_cash = expected
    row.counted_cash = money(data.counted_cash)
    row.difference = difference
    row.note = note
    row.closed_by = actor_id
    row.closed_at = now
    row.times_closed = (row.times_closed or 0) + 1
    row.updated_by = actor_id
    if existing is None:
        db.add(row)
    db.flush()
    closer = db.get(AppUser, actor_id)
    pdf = render_pdf(db, fig, row, closer.full_name if closer else "")
    key = pdf_key(fig.location_code, data.closing_date)
    try:
        get_storage().put(key, pdf)
    except (StorageError, OSError) as exc:
        db.rollback()
        raise AppError(
            "The closing PDF could not be saved. The day is not closed; try again.",
            code="STORAGE_FAILED",
        ) from exc
    row.pdf_key = key
    db.commit()
    return row


def reopen_day(db: Session, closing_id: int, data: ReopenIn, *, actor_id: int) -> DailyClosing:
    row = db.get(DailyClosing, closing_id)
    if row is None or row.tenant_id != TENANT_ID:
        raise NotFoundError("Closing not found")
    if row.status is not ClosingStatus.CLOSED:
        raise ConflictError("This day is not closed", code="NOT_CLOSED")
    row.status = ClosingStatus.REOPENED
    row.reopened_by = actor_id
    row.reopened_at = datetime.now(UTC)
    row.reopen_reason = data.reason
    row.updated_by = actor_id
    record_event(
        db,
        AuditAction.OVERRIDE,
        "daily_closing",
        row.id,
        {"reopened": row.closing_date.isoformat(), "reason": data.reason},
        user_id=actor_id,
    )
    db.commit()
    return row


def list_closings(
    db: Session, *, location_ids: frozenset[int] | None, limit: int, offset: int
) -> tuple[list[DailyClosing], int]:
    filters = [DailyClosing.tenant_id == TENANT_ID]
    if location_ids is not None:
        filters.append(DailyClosing.location_id.in_(location_ids))
    total = db.execute(select(func.count()).select_from(DailyClosing).where(*filters)).scalar_one()
    rows = db.execute(
        select(DailyClosing)
        .where(*filters)
        .order_by(DailyClosing.closing_date.desc(), DailyClosing.id.desc())
        .limit(limit)
        .offset(offset)
    ).scalars()
    return list(rows), total


def get_pdf(
    db: Session, closing_id: int, *, can_access: Callable[[int], bool]
) -> tuple[DailyClosing, bytes]:
    row = db.get(DailyClosing, closing_id)
    if (
        row is None
        or row.tenant_id != TENANT_ID
        or not can_access(row.location_id)
        or not row.pdf_key
    ):
        raise NotFoundError("Closing PDF not found")
    try:
        return row, get_storage().get(row.pdf_key)
    except StorageError as exc:
        raise NotFoundError("The saved PDF is missing from storage") from exc


def storage_name() -> str:
    return (
        "cloud storage" if get_settings().storage_provider is StorageProvider.S3 else "this server"
    )
