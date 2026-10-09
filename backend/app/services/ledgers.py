"""Writing to and reading from the append-only ledgers.

Every later milestone (purchases, sales, payments, returns) appends rows with `add_stock_move`
and `add_party_entry`, in the same transaction as its document. Balances, stock and average
cost are always recomputed from these rows by the domain functions."""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.tenancy import TENANT_ID
from app.domain import ledger as ledger_rules
from app.domain import stock_valuation
from app.domain.ledger import Account, LedgerEntry
from app.domain.money import ZERO, money
from app.models.enums import LedgerAccount, PartyRef, PartyType, StockRef
from app.models.ledgers import PartyLedger, StockLedger
from app.models.masters import Item, Party
from app.models.setup import Location
from app.schemas.ledger import (
    AccountOut,
    AgingOut,
    DuesOut,
    DuesRowOut,
    LedgerLineOut,
    StatementOut,
)
from app.schemas.stock import StockItemOut, StockItemOwnerOut, StockLocationOut

# ---------------------------------------------------------------------------- writing


def add_stock_move(
    db: Session,
    *,
    item_id: int,
    location_id: int,
    entry_date: date,
    qty_in: Decimal = ZERO,
    qty_out: Decimal = ZERO,
    unit_cost: Decimal,
    ref_type: StockRef,
    ref_id: int | None,
    narration: str | None = None,
    actor_id: int | None = None,
) -> StockLedger:
    row = StockLedger(
        tenant_id=TENANT_ID,
        item_id=item_id,
        location_id=location_id,
        entry_date=entry_date,
        qty_in=qty_in,
        qty_out=qty_out,
        unit_cost=unit_cost,
        ref_type=ref_type,
        ref_id=ref_id,
        narration=narration,
        created_by=actor_id,
    )
    db.add(row)
    return row


def add_party_entry(
    db: Session,
    *,
    party_id: int,
    site_id: int | None,
    account: LedgerAccount,
    entry_date: date,
    ref_type: PartyRef,
    ref_id: int | None,
    doc_no: str | None = None,
    applies_to: str | None = None,
    debit: Decimal = ZERO,
    credit: Decimal = ZERO,
    narration: str | None = None,
    actor_id: int | None = None,
) -> PartyLedger:
    row = PartyLedger(
        tenant_id=TENANT_ID,
        party_id=party_id,
        site_id=site_id,
        account=account,
        entry_date=entry_date,
        ref_type=ref_type,
        ref_id=ref_id,
        doc_no=doc_no,
        applies_to=applies_to,
        debit=debit,
        credit=credit,
        narration=narration,
        created_by=actor_id,
    )
    db.add(row)
    return row


# ---------------------------------------------------------------------------- stock


def lock_items(db: Session, item_ids: set[int]) -> None:
    """Serialise stock-out for these items until the transaction ends (rule B13).

    Two counters selling the last bag at once would otherwise both pass the stock check. The
    locks are taken in id order so two bills with the same items cannot deadlock."""
    for item_id in sorted(item_ids):
        db.execute(select(func.pg_advisory_xact_lock(item_id)))


def lock_party(db: Session, party_id: int) -> None:
    """Serialise bills for one customer so the credit limit is checked against the true balance."""
    db.execute(select(func.pg_advisory_xact_lock(2, party_id)))


def stock_position(
    db: Session, item_id: int, location_id: int | None = None
) -> tuple[stock_valuation.StockPosition, Decimal]:
    """(company-wide position, quantity at `location_id`) rebuilt from the ledger."""
    rows = db.execute(
        select(StockLedger)
        .where(StockLedger.tenant_id == TENANT_ID, StockLedger.item_id == item_id)
        .order_by(StockLedger.entry_date, StockLedger.id)
    ).scalars()
    moves = [
        stock_valuation.StockMove(
            r.entry_date, str(r.location_id), r.qty_in, r.qty_out, r.unit_cost
        )
        for r in rows
    ]
    result = stock_valuation.replay(moves)
    at_location = result.by_location.get(str(location_id), ZERO) if location_id else ZERO
    return result.total, at_location


def stock_summary(
    db: Session,
    *,
    with_cost: bool,
    location_id: int | None = None,
    q: str | None = None,
    include_zero: bool = False,
) -> list[StockItemOut | StockItemOwnerOut]:
    items = {
        i.id: i
        for i in db.execute(select(Item).where(Item.tenant_id == TENANT_ID)).scalars()
        if not q or q.lower() in f"{i.name} {i.brand or ''} {i.size or ''}".lower()
    }
    locations = {
        loc.id: loc
        for loc in db.execute(select(Location).where(Location.tenant_id == TENANT_ID)).scalars()
    }
    rows = db.execute(
        select(StockLedger)
        .where(StockLedger.tenant_id == TENANT_ID)
        .order_by(StockLedger.entry_date, StockLedger.id)
    ).scalars()
    moves: dict[int, list[stock_valuation.StockMove]] = {}
    for r in rows:
        if r.item_id in items:
            moves.setdefault(r.item_id, []).append(
                stock_valuation.StockMove(
                    r.entry_date, str(r.location_id), r.qty_in, r.qty_out, r.unit_cost
                )
            )

    out: list[StockItemOut | StockItemOwnerOut] = []
    for item_id, item_moves in moves.items():
        item = items[item_id]
        replay = stock_valuation.replay(item_moves)
        per_location = {int(k): v for k, v in replay.by_location.items()}
        if location_id is not None:
            per_location = {k: v for k, v in per_location.items() if k == location_id}
        total = sum(per_location.values(), ZERO)
        if total == ZERO and not include_zero:
            continue
        shown = [
            StockLocationOut(
                location_id=lid, code=locations[lid].code, name=locations[lid].name, quantity=qty
            )
            for lid, qty in sorted(per_location.items(), key=lambda kv: locations[kv[0]].code)
            if qty != ZERO or include_zero
        ]
        base = {
            "item_id": item.id,
            "name": item.name,
            "category": item.category,
            "base_unit": item.base_unit,
            "quantity": total,
            "locations": shown,
        }
        if with_cost:
            out.append(
                StockItemOwnerOut(
                    **base,
                    avg_cost=replay.total.avg_cost,
                    value=money(total * replay.total.avg_cost),
                )
            )
        else:
            out.append(StockItemOut(**base))
    return sorted(out, key=lambda r: r.name)


# ---------------------------------------------------------------------------- parties


def _account_view(rows: list[PartyLedger], account: LedgerAccount, today: date) -> AccountOut:
    domain_account = Account(account.value)
    entries = [
        LedgerEntry(
            r.entry_date, r.debit, r.credit, r.doc_no or str(r.ref_type.value), r.applies_to
        )
        for r in rows
    ]
    opened = ledger_rules.open_items(entries, domain_account)
    aged = ledger_rules.aging(opened, today)
    running = ZERO
    lines: list[LedgerLineOut] = []
    for r in rows:
        delta = r.debit - r.credit if account is LedgerAccount.RECEIVABLE else r.credit - r.debit
        running += delta
        lines.append(
            LedgerLineOut(
                id=r.id,
                entry_date=r.entry_date,
                ref_type=r.ref_type,
                doc_no=r.doc_no,
                site_id=r.site_id,
                debit=r.debit,
                credit=r.credit,
                running_balance=money(running),
                narration=r.narration,
            )
        )
    return AccountOut(
        account=account,
        balance=ledger_rules.balance(entries, domain_account),
        advance=opened.advance,
        aging=AgingOut(up_to_30=aged.up_to_30, days_31_60=aged.days_31_60, over_60=aged.over_60),
        entries=lines,
    )


def party_statement(
    db: Session,
    party_id: int,
    *,
    site_id: int | None,
    today: date,
    see_payable: bool,
) -> StatementOut:
    party = db.get(Party, party_id)
    if party is None or party.tenant_id != TENANT_ID:
        raise NotFoundError("Party not found")
    stmt = (
        select(PartyLedger)
        .where(PartyLedger.tenant_id == TENANT_ID, PartyLedger.party_id == party_id)
        .order_by(PartyLedger.entry_date, PartyLedger.id)
    )
    if site_id is not None:
        stmt = stmt.where(PartyLedger.site_id == site_id)
    rows = list(db.execute(stmt).scalars())
    by_account = {
        acct: [r for r in rows if r.account is acct]
        for acct in (LedgerAccount.RECEIVABLE, LedgerAccount.PAYABLE)
    }
    receivable = payable = None
    if party.type is not PartyType.SUPPLIER:
        receivable = _account_view(
            by_account[LedgerAccount.RECEIVABLE], LedgerAccount.RECEIVABLE, today
        )
    if party.type is not PartyType.CUSTOMER and see_payable:
        payable = _account_view(by_account[LedgerAccount.PAYABLE], LedgerAccount.PAYABLE, today)
    return StatementOut(
        party_id=party.id,
        party_name=party.name,
        site_id=site_id,
        receivable=receivable,
        payable=payable,
    )


def dues_report(db: Session, account: LedgerAccount, today: date) -> DuesOut:
    parties = {
        p.id: p for p in db.execute(select(Party).where(Party.tenant_id == TENANT_ID)).scalars()
    }
    rows = db.execute(
        select(PartyLedger)
        .where(PartyLedger.tenant_id == TENANT_ID, PartyLedger.account == account)
        .order_by(PartyLedger.entry_date, PartyLedger.id)
    ).scalars()
    grouped: dict[int, list[PartyLedger]] = {}
    for r in rows:
        grouped.setdefault(r.party_id, []).append(r)

    domain_account = Account(account.value)
    result: list[DuesRowOut] = []
    for party_id, party_rows in grouped.items():
        entries = [
            LedgerEntry(r.entry_date, r.debit, r.credit, r.doc_no or "", r.applies_to)
            for r in party_rows
        ]
        bal = ledger_rules.balance(entries, domain_account)
        opened = ledger_rules.open_items(entries, domain_account)
        if bal == ZERO and opened.advance == ZERO:
            continue
        aged = ledger_rules.aging(opened, today)
        result.append(
            DuesRowOut(
                party_id=party_id,
                party_name=parties[party_id].name,
                balance=bal,
                advance=opened.advance,
                aging=AgingOut(
                    up_to_30=aged.up_to_30, days_31_60=aged.days_31_60, over_60=aged.over_60
                ),
                oldest_date=min((i.entry_date for i in opened.items), default=None),
            )
        )
    result.sort(key=lambda r: (-r.balance, r.party_name))
    return DuesOut(
        account=account,
        as_of=today,
        total=money(sum((r.balance for r in result), ZERO)),
        rows=result,
    )
