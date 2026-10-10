"""Working capital for a month (FM5, docs/FINANCE_REVIEW.md F7): days inventory, sales and
payables outstanding, supplier advance days, the cash conversion cycle and the cash tied up.
Owner only. Nothing is stored: balances are rebuilt from the stock and party ledgers as at
each date, and flows from the bills, so the figures always agree with the books."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import today_ist
from app.core.errors import BusinessRuleError
from app.core.tenancy import TENANT_ID
from app.domain import finance
from app.domain import stock_valuation as stock_rules
from app.domain.money import ZERO, money
from app.models.enums import LedgerAccount, PartyRef
from app.models.ledgers import PartyLedger, StockLedger
from app.models.purchasing import Purchase
from app.models.returns import DebitNote
from app.models.sales import SalesInvoice
from app.schemas.finance import WorkingCapitalOut, WorkingCapitalPoint
from app.services import reports
from app.services.finance import month_bounds

MIN_DAYS = 7  # a month shorter than this has too little history to divide by
TREND_MONTHS = 6


def stock_values(db: Session, dates: list[date]) -> dict[date, Decimal]:
    """Stock at cost on each date: every item replayed up to that day, at one average cost per
    item for the whole business."""
    by_item: dict[int, list[StockLedger]] = defaultdict(list)
    rows = db.execute(
        select(StockLedger)
        .where(StockLedger.tenant_id == TENANT_ID)
        .order_by(StockLedger.entry_date, StockLedger.id)
    ).scalars()
    for row in rows:
        by_item[row.item_id].append(row)
    out: dict[date, Decimal] = {}
    for on in dates:
        total = ZERO
        for moves in by_item.values():
            upto = [
                stock_rules.StockMove(
                    r.entry_date, str(r.location_id), r.qty_in, r.qty_out, r.unit_cost
                )
                for r in moves
                if r.entry_date <= on
            ]
            if upto:
                total += stock_rules.replay(upto).total.value
        out[on] = money(total)
    return out


def party_balances(db: Session, dates: list[date]) -> dict[date, dict[str, Decimal]]:
    """For each date: customers' dues, customer advances, supplier dues and supplier advances,
    each summed over parties (a party in credit counts as an advance, not as a negative due)."""
    per_party: dict[tuple[LedgerAccount, int], list[tuple[date, Decimal]]] = defaultdict(list)
    for r in db.execute(select(PartyLedger).where(PartyLedger.tenant_id == TENANT_ID)).scalars():
        net = r.debit - r.credit if r.account is LedgerAccount.RECEIVABLE else r.credit - r.debit
        per_party[(r.account, r.party_id)].append((r.entry_date, net))
    out: dict[date, dict[str, Decimal]] = {}
    for on in dates:
        sums = {"receivables": ZERO, "payables": ZERO, "customer_advances": ZERO, "advances": ZERO}
        for (account, _), moves in per_party.items():
            balance = sum((n for d, n in moves if d <= on), ZERO)
            receivable = account is LedgerAccount.RECEIVABLE
            if balance >= ZERO:
                sums["receivables" if receivable else "payables"] += balance
            else:
                sums["customer_advances" if receivable else "advances"] += -balance
        out[on] = {k: money(v) for k, v in sums.items()}
    return out


def _flows(db: Session, date_from: date, date_to: date) -> dict[str, Decimal]:
    lines = reports._lines(db, date_from, date_to, None)
    cogs = money(sum((x.cost for x in lines), ZERO))
    credit_sales = db.execute(
        select(
            func.coalesce(func.sum(SalesInvoice.grand_total - SalesInvoice.paid_at_billing), 0)
        ).where(
            SalesInvoice.tenant_id == TENANT_ID,
            SalesInvoice.invoice_date >= date_from,
            SalesInvoice.invoice_date <= date_to,
        )
    ).scalar_one()
    bought = db.execute(
        select(func.coalesce(func.sum(Purchase.supplier_payable), 0)).where(
            Purchase.tenant_id == TENANT_ID,
            Purchase.bill_date >= date_from,
            Purchase.bill_date <= date_to,
        )
    ).scalar_one()
    returned = db.execute(
        select(func.coalesce(func.sum(DebitNote.grand_total), 0)).where(
            DebitNote.tenant_id == TENANT_ID,
            DebitNote.note_date >= date_from,
            DebitNote.note_date <= date_to,
        )
    ).scalar_one()
    taken_with_bills = db.execute(
        select(func.coalesce(func.sum(SalesInvoice.paid_at_billing), 0)).where(
            SalesInvoice.tenant_id == TENANT_ID,
            SalesInvoice.invoice_date >= date_from,
            SalesInvoice.invoice_date <= date_to,
        )
    ).scalar_one()
    collected = db.execute(
        select(func.coalesce(func.sum(PartyLedger.credit), 0)).where(
            PartyLedger.tenant_id == TENANT_ID,
            PartyLedger.account == LedgerAccount.RECEIVABLE,
            PartyLedger.ref_type == PartyRef.PAYMENT,
            PartyLedger.entry_date >= date_from,
            PartyLedger.entry_date <= date_to,
        )
    ).scalar_one()
    return {
        "cogs": cogs,
        "credit_sales": money(Decimal(credit_sales)),
        "purchases": money(Decimal(bought) - Decimal(returned)),
        # Money taken at the counter with the bill is not a collection: it never was credit.
        "collections": money(Decimal(collected) - Decimal(taken_with_bills)),
    }


def _first_document(db: Session) -> date | None:
    firsts = [
        db.execute(select(func.min(SalesInvoice.invoice_date))).scalar_one(),
        db.execute(select(func.min(Purchase.bill_date))).scalar_one(),
    ]
    known = [d for d in firsts if d is not None]
    return min(known) if known else None


def _periods_back(period: str, count: int) -> list[str]:
    year, month = (int(x) for x in period.split("-"))
    out = []
    for _ in range(count):
        out.append(f"{year}-{month:02d}")
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    return list(reversed(out))


def _month(*, period: str, today: date, first_doc: date | None) -> tuple[date, date, int, bool]:
    start, end = month_bounds(period)
    end = min(end, today)
    days = (end - start).days + 1
    if first_doc is None or first_doc > end:
        return start, end, days, False
    used = (end - max(start, first_doc)).days + 1
    return start, end, days, used >= MIN_DAYS


@dataclass(frozen=True)
class _Month:
    point: WorkingCapitalPoint
    cogs: Decimal
    credit_sales: Decimal
    purchases: Decimal
    collections: Decimal
    avg_stock: Decimal
    before: date  # the day before the period starts: opening balances are as at its end
    after: date  # the last day of the period


def working_capital(db: Session, period: str, *, with_trend: bool = True) -> WorkingCapitalOut:
    today = today_ist()
    start, _ = month_bounds(period)
    if start > today:
        raise BusinessRuleError("This month has not started yet", code="FUTURE_PERIOD")
    first_doc = _first_document(db)
    periods = _periods_back(period, TREND_MONTHS if with_trend else 1)
    spans = {p: _month(period=p, today=today, first_doc=first_doc) for p in periods}
    # Balances are taken at the end of the day before each month starts and at each month's end.
    dates = sorted({d for s, e, _, _ in spans.values() for d in (s - timedelta(days=1), e)})
    stock = stock_values(db, dates)
    balances = party_balances(db, dates)

    def figures(p: str) -> _Month:
        s, e, days, enough = spans[p]
        before = s - timedelta(days=1)
        flows = _flows(db, s, e)
        avg_stock = finance.average(stock[before], stock[e])
        avg_rec = finance.average(balances[before]["receivables"], balances[e]["receivables"])
        avg_pay = finance.average(balances[before]["payables"], balances[e]["payables"])
        avg_adv = finance.average(balances[before]["advances"], balances[e]["advances"])
        dio = finance.dio_days(avg_stock, flows["cogs"], days) if enough else None
        dso = finance.dso_days(avg_rec, flows["credit_sales"], days) if enough else None
        dpo = finance.dpo_days(avg_pay, flows["purchases"], days) if enough else None
        adv = finance.advance_days(avg_adv, flows["purchases"], days) if enough else None
        tied = finance.cash_tied_up(stock[e], balances[e]["receivables"], balances[e]["advances"])
        point = WorkingCapitalPoint(
            period=p,
            enough_data=enough,
            dio_days=dio,
            dso_days=dso,
            dpo_days=dpo,
            advance_days=adv,
            ccc_days=finance.ccc_days(dio, dso, adv, dpo),
            cash_tied_up=tied,
        )
        return _Month(
            point,
            flows["cogs"],
            flows["credit_sales"],
            flows["purchases"],
            flows["collections"],
            avg_stock,
            before,
            e,
        )

    months = {p: figures(p) for p in periods}
    m = months[period]
    s, e, days, enough = spans[period]
    note = None if enough else f"Not enough data yet (needs {MIN_DAYS} days of bills in the month)."
    return WorkingCapitalOut(
        period=period,
        date_from=s,
        date_to=e,
        days=days,
        enough_data=enough,
        data_note=note,
        stock_start=stock[m.before],
        stock_end=stock[m.after],
        receivables_start=balances[m.before]["receivables"],
        receivables_end=balances[m.after]["receivables"],
        payables_start=balances[m.before]["payables"],
        payables_end=balances[m.after]["payables"],
        advances_start=balances[m.before]["advances"],
        advances_end=balances[m.after]["advances"],
        cogs=m.cogs,
        credit_sales=m.credit_sales,
        purchases=m.purchases,
        collections=m.collections,
        dio_days=m.point.dio_days,
        dso_days=m.point.dso_days,
        dpo_days=m.point.dpo_days,
        advance_days=m.point.advance_days,
        ccc_days=m.point.ccc_days,
        inventory_turnover=finance.inventory_turnover(m.cogs, m.avg_stock) if enough else None,
        collection_efficiency_pct=finance.collection_efficiency_pct(
            m.collections, balances[m.before]["receivables"], m.credit_sales
        )
        if enough
        else None,
        cash_tied_up=m.point.cash_tied_up,
        working_capital=finance.working_capital(
            m.point.cash_tied_up, balances[m.after]["payables"]
        ),
        trend=[months[p].point for p in periods] if with_trend else [],
    )
