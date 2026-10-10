"""Receivables by due date and bad-debt write-offs (FM5, docs/FINANCE_REVIEW.md F8, F9).

Aging counts from each bill's due date, not its bill date. Everything is rebuilt from the party
ledger and the bills on each request. A write-off is an owner-only document that credits the
customer's account with no GST effect; it is never a credit note."""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import today_ist
from app.core.errors import BusinessRuleError, NotFoundError
from app.core.tenancy import TENANT_ID
from app.domain import finance
from app.domain import ledger as ledger_rules
from app.domain.finance import OverdueBucket
from app.domain.ledger import Account, LedgerEntry
from app.domain.money import ZERO, money
from app.models.enums import DocType, LedgerAccount, PartyRef, PartyType
from app.models.ledgers import PartyLedger
from app.models.masters import Party
from app.models.receivables import BadDebtWriteoff
from app.models.sales import SalesInvoice
from app.models.setup import AppUser, Location, ShopSettings
from app.schemas.receivables import (
    BucketsOut,
    ReceivableRowOut,
    ReceivablesOut,
    ReceivablesOwnerOut,
    WriteoffCreate,
    WriteoffOut,
)
from app.services import ledgers
from app.services.numbering import allocate_number
from app.services.shop_settings import get_settings_row

DSO_WINDOW_DAYS = 90


def _buckets(values: dict[OverdueBucket, Decimal]) -> BucketsOut:
    return BucketsOut(
        current=values[OverdueBucket.CURRENT],
        days_1_15=values[OverdueBucket.DAYS_1_15],
        days_16_30=values[OverdueBucket.DAYS_16_30],
        days_31_60=values[OverdueBucket.DAYS_31_60],
        over_60=values[OverdueBucket.OVER_60],
    )


def provision_pct(settings: ShopSettings) -> dict[OverdueBucket, Decimal]:
    return {
        OverdueBucket.CURRENT: settings.provision_pct_current,
        OverdueBucket.DAYS_1_15: settings.provision_pct_1_15,
        OverdueBucket.DAYS_16_30: settings.provision_pct_16_30,
        OverdueBucket.DAYS_31_60: settings.provision_pct_31_60,
        OverdueBucket.OVER_60: settings.provision_pct_over_60,
    }


def receivable_entries(db: Session) -> dict[int, list[PartyLedger]]:
    rows = db.execute(
        select(PartyLedger)
        .where(PartyLedger.tenant_id == TENANT_ID, PartyLedger.account == LedgerAccount.RECEIVABLE)
        .order_by(PartyLedger.entry_date, PartyLedger.id)
    ).scalars()
    grouped: dict[int, list[PartyLedger]] = defaultdict(list)
    for row in rows:
        grouped[row.party_id].append(row)
    return grouped


def _entries(rows: list[PartyLedger]) -> list[LedgerEntry]:
    return [
        LedgerEntry(r.entry_date, r.debit, r.credit, r.doc_no or "", r.applies_to) for r in rows
    ]


def receivables_report(db: Session, today: date, *, owner: bool) -> ReceivablesOut:
    settings = get_settings_row(db)
    parties = {
        p.id: p for p in db.execute(select(Party).where(Party.tenant_id == TENANT_ID)).scalars()
    }
    # Bills carry their own due date; anything else (an opening balance) is due the day it starts.
    due = {
        i.number: i.due_date or i.invoice_date
        for i in db.execute(
            select(SalesInvoice).where(SalesInvoice.tenant_id == TENANT_ID)
        ).scalars()
    }
    window_start = today - timedelta(days=DSO_WINDOW_DAYS)
    credit_sales: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for party_id, grand, paid in db.execute(
        select(SalesInvoice.party_id, SalesInvoice.grand_total, SalesInvoice.paid_at_billing).where(
            SalesInvoice.tenant_id == TENANT_ID, SalesInvoice.invoice_date > window_start
        )
    ).all():
        credit_sales[party_id] += grand - paid

    rows: list[ReceivableRowOut] = []
    all_items: list[finance.OverdueItem] = []
    advances = ZERO
    total = ZERO
    for party_id, ledger_rows in receivable_entries(db).items():
        entries = _entries(ledger_rows)
        balance = ledger_rules.balance(entries, Account.RECEIVABLE)
        opened = ledger_rules.open_items(entries, Account.RECEIVABLE)
        if balance == ZERO and opened.advance == ZERO:
            continue
        items = [
            finance.OverdueItem(due.get(i.ref, i.entry_date), i.remaining) for i in opened.items
        ]
        all_items += items
        aged = finance.overdue_aging(items, today)
        late = [i.due_date for i in items if i.due_date < today]
        party = parties[party_id]
        limit: Decimal | None = None
        if party.credit_allowed:
            limit = (
                party.credit_limit
                if party.credit_limit is not None
                else settings.default_credit_limit
            )
        started = ledger_rules.balance(
            [e for e in entries if e.entry_date <= window_start], Account.RECEIVABLE
        )
        dso = finance.dso_days(
            finance.average(max(started, ZERO), max(balance, ZERO)),
            credit_sales.get(party_id, ZERO),
            DSO_WINDOW_DAYS,
        )
        payments = [r.entry_date for r in ledger_rows if r.ref_type is PartyRef.PAYMENT]
        total += max(balance, ZERO)
        advances += opened.advance
        rows.append(
            ReceivableRowOut(
                party_id=party_id,
                party_name=party.name,
                balance=balance,
                advance=opened.advance,
                overdue=finance.overdue_total(aged),
                buckets=_buckets(aged),
                oldest_due_date=min(late) if late else None,
                days_late=(today - min(late)).days if late else None,
                credit_limit=limit,
                utilisation_pct=finance.credit_utilisation_pct(max(balance, ZERO), limit)
                if limit is not None
                else None,
                dso_days=dso,
                last_payment_date=max(payments) if payments else None,
            )
        )
    rows.sort(key=lambda r: (-r.overdue, -r.balance, r.party_name))
    aged_all = finance.overdue_aging(all_items, today)
    common = {
        "as_of": today,
        "total": money(total),
        "advances": money(advances),
        "overdue": finance.overdue_total(aged_all),
        "buckets": _buckets(aged_all),
        "rows": rows,
    }
    if not owner:
        return ReceivablesOut(**common)
    pct = provision_pct(settings)
    return ReceivablesOwnerOut(
        **common,
        provision=finance.provision(aged_all, pct),
        provision_pct=_buckets(pct),
    )


# ------------------------------------------------------------------------------ write-offs


def _view(db: Session, row: BadDebtWriteoff) -> WriteoffOut:
    party = db.get(Party, row.party_id)
    who = db.get(AppUser, row.created_by) if row.created_by else None
    return WriteoffOut(
        id=row.id,
        number=row.number,
        location_id=row.location_id,
        party_id=row.party_id,
        party_name=party.name if party else "",
        writeoff_date=row.writeoff_date,
        amount=row.amount,
        balance_before=row.balance_before,
        reason=row.reason,
        created_by_name=who.full_name if who else None,
    )


def create_writeoff(db: Session, data: WriteoffCreate, *, actor_id: int) -> WriteoffOut:
    place = db.get(Location, data.location_id)
    if place is None or place.tenant_id != TENANT_ID or not place.is_active:
        raise NotFoundError("Shop not found", field="location_id")
    party = db.get(Party, data.party_id)
    if party is None or party.tenant_id != TENANT_ID:
        raise NotFoundError("Customer not found", field="party_id")
    if party.type is PartyType.SUPPLIER:
        raise BusinessRuleError(
            "Only a customer's debt can be written off", code="NOT_A_CUSTOMER", field="party_id"
        )
    ledgers.lock_party(db, party.id)
    entries = _entries(receivable_entries(db).get(party.id, []))
    balance = ledger_rules.balance(entries, Account.RECEIVABLE)
    if not finance.can_write_off(balance, data.amount):
        raise BusinessRuleError(
            f"{party.name} does not owe that much. A write-off can only be for what they owe.",
            code="WRITEOFF_TOO_MUCH",
            field="amount",
        )
    settings = get_settings_row(db)
    today = today_ist()
    number = allocate_number(
        db,
        location_id=place.id,
        doc_type=DocType.BAD_DEBT_WRITEOFF,
        on=today,
        fy_start_month=settings.financial_year_start_month,
    )
    row = BadDebtWriteoff(
        tenant_id=TENANT_ID,
        number=number,
        location_id=place.id,
        party_id=party.id,
        writeoff_date=today,
        amount=money(data.amount),
        balance_before=balance,
        reason=data.reason.strip(),
        created_by=actor_id,
    )
    db.add(row)
    db.flush()
    ledgers.add_party_entry(
        db,
        party_id=party.id,
        site_id=None,
        account=LedgerAccount.RECEIVABLE,
        entry_date=today,
        ref_type=PartyRef.WRITE_OFF,
        ref_id=row.id,
        doc_no=number,
        credit=row.amount,
        narration=f"Bad debt written off: {row.reason}",
        actor_id=actor_id,
    )
    db.commit()
    return _view(db, row)


def list_writeoffs(
    db: Session, *, party_id: int | None, date_from: date | None, date_to: date | None
) -> list[WriteoffOut]:
    stmt = select(BadDebtWriteoff).where(BadDebtWriteoff.tenant_id == TENANT_ID)
    if party_id is not None:
        stmt = stmt.where(BadDebtWriteoff.party_id == party_id)
    if date_from is not None:
        stmt = stmt.where(BadDebtWriteoff.writeoff_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(BadDebtWriteoff.writeoff_date <= date_to)
    rows = db.execute(stmt.order_by(BadDebtWriteoff.id.desc())).scalars()
    return [_view(db, r) for r in rows]


def written_off(db: Session, date_from: date, date_to: date, location_id: int | None) -> Decimal:
    """Bad debts written off in a period, for the profit and loss."""
    stmt = select(BadDebtWriteoff.amount).where(
        BadDebtWriteoff.tenant_id == TENANT_ID,
        BadDebtWriteoff.writeoff_date >= date_from,
        BadDebtWriteoff.writeoff_date <= date_to,
    )
    if location_id is not None:
        stmt = stmt.where(BadDebtWriteoff.location_id == location_id)
    return money(sum(db.execute(stmt).scalars(), ZERO))
