"""Credit control at billing (rule B8): a few approved customers, a limit and a number of days."""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenancy import TENANT_ID
from app.domain import credit as credit_rules
from app.domain import ledger as ledger_rules
from app.domain.ledger import Account, LedgerEntry
from app.models.enums import LedgerAccount
from app.models.ledgers import PartyLedger
from app.models.masters import Party
from app.models.sales import SalesInvoice
from app.models.setup import ShopSettings


def open_bills(
    db: Session, party: Party, settings: ShopSettings, today: date
) -> tuple[list[credit_rules.OpenInvoice], Decimal]:
    """Unpaid bills with their due dates, and any advance held, after payments are applied."""
    rows = db.execute(
        select(PartyLedger)
        .where(
            PartyLedger.tenant_id == TENANT_ID,
            PartyLedger.party_id == party.id,
            PartyLedger.account == LedgerAccount.RECEIVABLE,
        )
        .order_by(PartyLedger.entry_date, PartyLedger.id)
    ).scalars()
    entries = [
        LedgerEntry(r.entry_date, r.debit, r.credit, r.doc_no or "", r.applies_to) for r in rows
    ]
    opened = ledger_rules.open_items(entries, Account.RECEIVABLE)
    due_by_number = dict(
        db.execute(
            select(SalesInvoice.number, SalesInvoice.due_date).where(
                SalesInvoice.tenant_id == TENANT_ID, SalesInvoice.party_id == party.id
            )
        ).all()
    )
    days = party.credit_days if party.credit_days is not None else settings.default_credit_days
    bills = [
        credit_rules.OpenInvoice(
            number=item.ref,
            invoice_date=item.entry_date,
            due_date=due_by_number.get(item.ref) or item.entry_date + timedelta(days=days),
            balance=item.remaining,
        )
        for item in opened.items
    ]
    _ = today
    return bills, opened.advance


def decide(
    db: Session, party: Party, settings: ShopSettings, unpaid: Decimal, today: date
) -> credit_rules.CreditDecision:
    policy = credit_rules.CreditPolicy(
        credit_allowed=party.credit_allowed,
        limit=party.credit_limit
        if party.credit_limit is not None
        else settings.default_credit_limit,
        days=party.credit_days if party.credit_days is not None else settings.default_credit_days,
    )
    bills, _ = open_bills(db, party, settings, today)
    return credit_rules.check_credit(policy, bills, unpaid, today)
