"""Owner exception report (FM7, docs/FINANCE_REVIEW.md F17): entries that look like the usual ways
money or stock goes missing. Each rule is a question asked of the books when the report is read;
nothing is stored. A flag is a reason to look, not a finding. Thresholds are shop settings and a
zero switches a rule off."""

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime, timedelta

from sqlalchemy import ColumnElement, Date, cast, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.core.errors import BusinessRuleError
from app.core.tenancy import TENANT_ID
from app.domain import controls as rules
from app.domain.money import ZERO, money
from app.models.cashbook import CashEntry
from app.models.enums import PaymentDirection, PaymentMode
from app.models.masters import Party
from app.models.purchasing import Payment, Purchase, PurchaseLine
from app.models.returns import CreditNote
from app.models.sales import SalesInvoice
from app.models.setup import AppUser, Location, ShopSettings
from app.models.stock_ops import StockAdjustment, StockCount
from app.schemas.controls import ExceptionCount, ExceptionReport, ExceptionRow
from app.services.shop_settings import get_settings_row

TITLES = {
    "round_adjustment": "Round-number stock adjustment",
    "adjustment_before_count": "Adjustment just before a stock count",
    "repeat_returns": "Many returns from one customer",
    "back_dated": "Entry dated well before it was keyed in",
    "cash_near_limit": "Cash near the daily limit",
    "repeat_shortage": "Repeated weighbridge shortages from one supplier",
}
SHORTAGE_DAYS = 90
BACKDATE_MIN_DAYS = 1


def _ist_date(column: InstrumentedAttribute[datetime]) -> ColumnElement[date]:
    """The day a row was keyed in, in Indian time."""
    return cast(func.timezone("Asia/Kolkata", column), Date)


class _Ctx:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = {u.id: u.full_name for u in db.scalars(select(AppUser))}
        self.places = {p.id: p.code for p in db.scalars(select(Location))}

    def who(self, user_id: int | None) -> str | None:
        return self.users.get(user_id) if user_id is not None else None

    def place(self, location_id: int | None) -> str | None:
        return self.places.get(location_id) if location_id is not None else None


def _row(code: str, ctx: _Ctx, **kw: object) -> ExceptionRow:
    return ExceptionRow(code=code, title=TITLES[code], **kw)


def _round_and_before_count(
    ctx: _Ctx, s: ShopSettings, date_from: date, date_to: date
) -> Iterable[ExceptionRow]:
    adjustments = ctx.db.scalars(
        select(StockAdjustment).where(
            StockAdjustment.tenant_id == TENANT_ID,
            StockAdjustment.adjustment_date >= date_from,
            StockAdjustment.adjustment_date <= date_to,
        )
    ).all()
    counts: dict[int, list[date]] = defaultdict(list)
    if s.exception_count_days > 0 and adjustments:
        for loc, on in ctx.db.execute(
            select(StockCount.location_id, StockCount.count_date).where(
                StockCount.tenant_id == TENANT_ID,
                StockCount.count_date >= date_from,
                StockCount.count_date <= date_to + timedelta(days=s.exception_count_days),
            )
        ):
            counts[loc].append(on)
    for adj in adjustments:
        value = money(sum((x.quantity * x.unit_cost for x in adj.lines), ZERO))
        base = {
            "on": adj.adjustment_date,
            "location_code": ctx.place(adj.location_id),
            "user_name": ctx.who(adj.created_by),
            "document": adj.number,
            "value": value,
            "link": "/stock/adjustments",
        }
        if rules.is_round(value, s.exception_round_amount):
            yield _row(
                "round_adjustment",
                ctx,
                detail=f"Worth exactly ₹{value:,.0f} ({adj.reason.value.replace('_', ' ')}).",
                **base,
            )
        if s.exception_count_days > 0:
            gaps = [
                g
                for on in counts.get(adj.location_id, [])
                if (g := rules.days_before(adj.adjustment_date, on, s.exception_count_days))
                is not None
            ]
            if gaps:
                nearest = min(gaps)
                when = "the same day as" if nearest == 0 else f"{nearest} day(s) before"
                yield _row(
                    "adjustment_before_count",
                    ctx,
                    detail=f"Posted {when} a stock count at this place.",
                    **base,
                )


def _repeat_returns(
    ctx: _Ctx, s: ShopSettings, date_from: date, date_to: date
) -> Iterable[ExceptionRow]:
    if s.exception_returns_count <= 0:
        return
    since = date_from - timedelta(days=s.exception_returns_days)
    rows = ctx.db.execute(
        select(CreditNote.party_id, CreditNote.note_date, CreditNote.created_by)
        .where(
            CreditNote.tenant_id == TENANT_ID,
            CreditNote.note_date >= since,
            CreditNote.note_date <= date_to,
        )
        .order_by(CreditNote.note_date)
    ).all()
    per: dict[int, list[date]] = defaultdict(list)
    users: dict[int, int | None] = {}
    for party_id, on, user in rows:
        per[party_id].append(on)
        users[party_id] = user
    names = {p.id: p.name for p in ctx.db.scalars(select(Party).where(Party.id.in_(per)))}
    for party_id, dates in per.items():
        remaining = dates
        while (
            run := rules.repeated_within(
                remaining, s.exception_returns_count, s.exception_returns_days
            )
        ) is not None:
            first, last, n = run
            if last >= date_from:
                yield _row(
                    "repeat_returns",
                    ctx,
                    on=last,
                    location_code=None,
                    user_name=ctx.who(users[party_id]),
                    document=None,
                    detail=(
                        f"{names.get(party_id, 'A customer')}: {n} credit notes between "
                        f"{first:%d-%m-%Y} and {last:%d-%m-%Y}."
                    ),
                    value=None,
                    link="/sales",
                )
                break
            remaining = [d for d in remaining if d > last]


def _back_dated(
    ctx: _Ctx, s: ShopSettings, date_from: date, date_to: date
) -> Iterable[ExceptionRow]:
    kinds = (
        ("invoice", SalesInvoice, SalesInvoice.invoice_date, SalesInvoice.number, "/sales"),
        ("receipt", Payment, Payment.payment_date, Payment.number, "/payments"),
        ("voucher", CashEntry, CashEntry.entry_date, CashEntry.number, "/cash"),
        (
            "adjustment",
            StockAdjustment,
            StockAdjustment.adjustment_date,
            StockAdjustment.number,
            "/stock/adjustments",
        ),
    )
    for label, model, date_col, number_col, link in kinds:
        keyed = _ist_date(model.created_at)
        found = ctx.db.execute(
            select(date_col, keyed, number_col, model.location_id, model.created_by).where(
                model.tenant_id == TENANT_ID,
                date_col >= date_from,
                date_col <= date_to,
                keyed - date_col >= BACKDATE_MIN_DAYS,
            )
        ).all()
        for doc_date, keyed_on, number, location_id, user in found:
            days = rules.backdated_days(doc_date, keyed_on)
            yield _row(
                "back_dated",
                ctx,
                on=doc_date,
                location_code=ctx.place(location_id),
                user_name=ctx.who(user),
                document=number,
                detail=(
                    f"A {label} dated {days} day(s) before it was keyed in ({keyed_on:%d-%m-%Y})."
                ),
                value=None,
                link=link,
            )


def _cash_near_limit(
    ctx: _Ctx, s: ShopSettings, date_from: date, date_to: date
) -> Iterable[ExceptionRow]:
    if s.exception_cash_near_pct <= 0 or s.cash_receipt_limit <= 0:
        return
    rows = ctx.db.execute(
        select(
            Payment.party_id,
            Payment.payment_date,
            func.sum(Payment.amount),
            func.max(Payment.location_id),
            func.max(Payment.created_by),
        )
        .where(
            Payment.tenant_id == TENANT_ID,
            Payment.direction == PaymentDirection.RECEIVED,
            Payment.mode == PaymentMode.CASH,
            Payment.payment_date >= date_from,
            Payment.payment_date <= date_to,
        )
        .group_by(Payment.party_id, Payment.payment_date)
    ).all()
    names = {p.id: p.name for p in ctx.db.scalars(select(Party))}
    for party_id, on, total, location_id, user in rows:
        if rules.near_limit(total, s.cash_receipt_limit, s.exception_cash_near_pct):
            yield _row(
                "cash_near_limit",
                ctx,
                on=on,
                location_code=ctx.place(location_id),
                user_name=ctx.who(user),
                document=None,
                detail=(
                    f"{names.get(party_id, 'A customer')} paid ₹{money(total):,.0f} in cash in a "
                    f"day; the limit is ₹{s.cash_receipt_limit:,.0f}."
                ),
                value=money(total),
                link="/payments",
            )


def _repeat_shortages(
    ctx: _Ctx, s: ShopSettings, date_from: date, date_to: date
) -> Iterable[ExceptionRow]:
    if s.exception_shortage_count <= 0:
        return
    since = date_to - timedelta(days=SHORTAGE_DAYS)
    rows = ctx.db.execute(
        select(Purchase.supplier_id, func.count(), func.max(Purchase.bill_date))
        .join(PurchaseLine, PurchaseLine.purchase_id == Purchase.id)
        .where(
            Purchase.tenant_id == TENANT_ID,
            Purchase.bill_date >= since,
            Purchase.bill_date <= date_to,
            PurchaseLine.received_qty < PurchaseLine.billed_qty,
        )
        .group_by(Purchase.supplier_id)
    ).all()
    names = {p.id: p.name for p in ctx.db.scalars(select(Party))}
    for supplier_id, n, last in rows:
        if n >= s.exception_shortage_count and last >= date_from:
            yield _row(
                "repeat_shortage",
                ctx,
                on=last,
                location_code=None,
                user_name=None,
                document=None,
                detail=(
                    f"{names.get(supplier_id, 'A supplier')}: weighbridge showed less than "
                    f"billed on {n} lines in {SHORTAGE_DAYS} days."
                ),
                value=None,
                link="/stock/shrinkage",
            )


def exception_report(db: Session, date_from: date, date_to: date) -> ExceptionReport:
    if date_to < date_from:
        raise BusinessRuleError(
            "The end date is before the start date", code="BAD_RANGE", field="date_to"
        )
    if (date_to - date_from).days > 366:
        raise BusinessRuleError(
            "Pick a range of a year or less", code="RANGE_TOO_LONG", field="date_to"
        )
    s = get_settings_row(db)
    ctx = _Ctx(db)
    rows: list[ExceptionRow] = [
        *_round_and_before_count(ctx, s, date_from, date_to),
        *_repeat_returns(ctx, s, date_from, date_to),
        *_back_dated(ctx, s, date_from, date_to),
        *_cash_near_limit(ctx, s, date_from, date_to),
        *_repeat_shortages(ctx, s, date_from, date_to),
    ]
    rows.sort(key=lambda r: (r.on, r.code, r.document or ""), reverse=True)
    counts = [
        ExceptionCount(code=code, title=title, count=sum(1 for r in rows if r.code == code))
        for code, title in TITLES.items()
    ]
    return ExceptionReport(date_from=date_from, date_to=date_to, rows=rows, counts=counts)
