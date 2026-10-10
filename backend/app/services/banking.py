"""Bank statements and reconciliation (FM7, docs/FINANCE_REVIEW.md F16).

A statement CSV is stored as the bank sent it. Which line matches which receipt is worked out
when the report is read (`domain/controls.match_statement`), so nothing goes stale when a
receipt is keyed in late. The books side is every receipt, supplier payment and cash-book entry
that moved money through a bank or UPI, and every cash deposit or withdrawal."""

import hashlib
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.tenancy import TENANT_ID
from app.domain import controls as rules
from app.domain.finance import CashEntryKind
from app.domain.money import ZERO, money
from app.models.banking import BankAccount, BankStatement, BankStatementLine
from app.models.cashbook import CashEntry
from app.models.enums import PaymentDirection, PaymentMode
from app.models.masters import Party
from app.models.purchasing import Payment
from app.models.setup import AppUser
from app.schemas.controls import (
    BankAccountCreate,
    BankAccountOut,
    BankAccountUpdate,
    BankLineOut,
    BankStatementOut,
    BookEntryOut,
    ReconciliationOut,
)
from app.services.shop_settings import get_settings_row

# --------------------------------------------------------------------------- accounts


def _account(db: Session, account_id: int) -> BankAccount:
    row = db.get(BankAccount, account_id)
    if row is None or row.tenant_id != TENANT_ID:
        raise NotFoundError("Bank account not found", field="bank_account_id")
    return row


def list_accounts(db: Session) -> list[BankAccountOut]:
    rows = db.scalars(
        select(BankAccount).where(BankAccount.tenant_id == TENANT_ID).order_by(BankAccount.name)
    )
    return [BankAccountOut.model_validate(r) for r in rows]


def _name_free(db: Session, name: str, except_id: int | None = None) -> None:
    stmt = select(BankAccount.id).where(
        BankAccount.tenant_id == TENANT_ID, BankAccount.name == name
    )
    if except_id is not None:
        stmt = stmt.where(BankAccount.id != except_id)
    if db.execute(stmt).first() is not None:
        raise ConflictError("A bank account with this name already exists", code="DUPLICATE_NAME")


def create_account(db: Session, data: BankAccountCreate, *, actor_id: int) -> BankAccountOut:
    _name_free(db, data.name)
    row = BankAccount(
        tenant_id=TENANT_ID,
        name=data.name,
        account_no_last4=data.account_no_last4,
        is_active=True,
        created_by=actor_id,
    )
    db.add(row)
    db.commit()
    return BankAccountOut.model_validate(row)


def update_account(
    db: Session, account_id: int, data: BankAccountUpdate, *, actor_id: int
) -> BankAccountOut:
    row = _account(db, account_id)
    if data.name is not None and data.name != row.name:
        _name_free(db, data.name, row.id)
        row.name = data.name
    if data.is_active is not None:
        row.is_active = data.is_active
    row.updated_by = actor_id
    db.commit()
    return BankAccountOut.model_validate(row)


# --------------------------------------------------------------------------- import


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("latin-1")


def _line_key(on: date, narration: str, reference: str, debit: Decimal, credit: Decimal):  # type: ignore[no-untyped-def]
    return (on, narration, reference, debit, credit)


def _view_statement(db: Session, row: BankStatement) -> BankStatementOut:
    account = db.get(BankAccount, row.bank_account_id)
    who = db.get(AppUser, row.created_by) if row.created_by else None
    return BankStatementOut(
        id=row.id,
        bank_account_id=row.bank_account_id,
        bank_account_name=account.name if account else "",
        filename=row.filename,
        from_date=row.from_date,
        to_date=row.to_date,
        row_count=row.row_count,
        skipped_count=row.skipped_count,
        closing_balance=row.closing_balance,
        imported_at=row.created_at,
        imported_by_name=who.full_name if who else None,
    )


def import_statement(
    db: Session, account_id: int, filename: str, content: bytes, *, actor_id: int
) -> BankStatementOut:
    account = _account(db, account_id)
    if not account.is_active:
        raise BusinessRuleError("This bank account is switched off", code="ACCOUNT_INACTIVE")
    digest = hashlib.sha256(content).hexdigest()
    again = db.execute(
        select(BankStatement.id).where(
            BankStatement.tenant_id == TENANT_ID,
            BankStatement.bank_account_id == account.id,
            BankStatement.file_sha256 == digest,
        )
    ).first()
    if again is not None:
        raise ConflictError(
            "This file was already imported for this account", code="STATEMENT_IMPORTED"
        )
    parsed = rules.parse_bank_csv(_decode(content))
    if parsed.errors:
        shown = "; ".join(parsed.errors[:5])
        more = f" (and {len(parsed.errors) - 5} more)" if len(parsed.errors) > 5 else ""
        raise BusinessRuleError(
            f"The file could not be read, so nothing was imported. {shown}{more}",
            code="STATEMENT_UNREADABLE",
            field="file",
        )
    if not parsed.rows:
        raise BusinessRuleError(
            "The file has no transactions", code="STATEMENT_EMPTY", field="file"
        )

    # Overlapping downloads repeat old lines: a line already held is skipped. Identical lines on
    # one day (same amount and narration) are counted, so two real ones are both kept.
    held: Counter[tuple] = Counter()  # type: ignore[type-arg]
    lo = min(r.on for r in parsed.rows)
    hi = max(r.on for r in parsed.rows)
    for ln in db.scalars(
        select(BankStatementLine)
        .join(BankStatement, BankStatement.id == BankStatementLine.statement_id)
        .where(
            BankStatement.bank_account_id == account.id,
            BankStatementLine.line_date >= lo,
            BankStatementLine.line_date <= hi,
        )
    ):
        held[_line_key(ln.line_date, ln.narration, ln.reference, ln.debit, ln.credit)] += 1
    seen: Counter[tuple] = Counter()  # type: ignore[type-arg]
    fresh: list[rules.BankRow] = []
    for r in parsed.rows:
        key = _line_key(r.on, r.narration[:300], r.reference[:60], r.debit, r.credit)
        seen[key] += 1
        if seen[key] > held[key]:
            fresh.append(r)
    last = max(parsed.rows, key=lambda r: (r.on, r.line_no))
    statement = BankStatement(
        tenant_id=TENANT_ID,
        bank_account_id=account.id,
        filename=filename[:200] or "statement.csv",
        file_sha256=digest,
        from_date=lo,
        to_date=hi,
        row_count=len(parsed.rows),
        skipped_count=len(parsed.rows) - len(fresh),
        closing_balance=last.balance,
        created_by=actor_id,
    )
    db.add(statement)
    db.flush()
    for r in fresh:
        db.add(
            BankStatementLine(
                tenant_id=TENANT_ID,
                statement_id=statement.id,
                line_no=r.line_no,
                line_date=r.on,
                narration=r.narration[:300],
                reference=r.reference[:60],
                debit=r.debit,
                credit=r.credit,
                balance=r.balance,
            )
        )
    try:
        db.commit()
    except IntegrityError as exc:  # two uploads of one file at the same moment
        db.rollback()
        raise ConflictError(
            "This file was already imported for this account", code="STATEMENT_IMPORTED"
        ) from exc
    return _view_statement(db, statement)


def list_statements(db: Session) -> list[BankStatementOut]:
    rows = db.scalars(
        select(BankStatement)
        .where(BankStatement.tenant_id == TENANT_ID)
        .order_by(BankStatement.id.desc())
    )
    return [_view_statement(db, r) for r in rows]


# --------------------------------------------------------------------------- reconciliation

_MODE_LABEL = {PaymentMode.CASH: "cash", PaymentMode.UPI: "UPI", PaymentMode.BANK: "bank"}


def books_in_range(
    db: Session, date_from: date, date_to: date
) -> list[tuple[rules.BookEntry, str, str]]:
    """Everything the books say passed through the bank between two dates: (entry, label, mode)."""
    out: list[tuple[rules.BookEntry, str, str]] = []
    pays = db.execute(
        select(Payment, Party.name)
        .join(Party, Party.id == Payment.party_id)
        .where(
            Payment.tenant_id == TENANT_ID,
            Payment.mode != PaymentMode.CASH,
            Payment.payment_date >= date_from,
            Payment.payment_date <= date_to,
        )
    ).all()
    for p, party in pays:
        received = p.direction is PaymentDirection.RECEIVED
        out.append(
            (
                rules.BookEntry(f"payment:{p.id}", p.payment_date, p.amount, received, p.reference),
                f"{'Receipt' if received else 'Payment'} {p.number}, {party}",
                _MODE_LABEL[p.mode],
            )
        )
    entries = db.scalars(
        select(CashEntry).where(
            CashEntry.tenant_id == TENANT_ID,
            CashEntry.entry_date >= date_from,
            CashEntry.entry_date <= date_to,
        )
    ).all()
    reversed_ids = {e.reverses_id for e in entries if e.reverses_id is not None}
    reversed_ids |= set(
        db.scalars(
            select(CashEntry.reverses_id).where(
                CashEntry.tenant_id == TENANT_ID, CashEntry.reverses_id.is_not(None)
            )
        )
    )
    for e in entries:
        if e.id in reversed_ids or e.reverses_id is not None:
            continue  # a voucher and its reversal cancel out; the bank sees neither
        if e.kind is CashEntryKind.BANK_DEPOSIT:
            money_in, label = True, f"Cash deposit {e.number}"
        elif e.kind is CashEntryKind.BANK_WITHDRAWAL:
            money_in, label = False, f"Cash withdrawal {e.number}"
        elif e.mode is PaymentMode.CASH:
            continue  # notes in the drawer never touch the bank
        elif e.kind is CashEntryKind.OWNER_CAPITAL:
            money_in, label = True, f"Owner's money in {e.number}"
        else:
            money_in = False
            label = f"{'Expense' if e.kind is CashEntryKind.EXPENSE else 'Drawing'} {e.number}"
            if e.paid_to:
                label += f", {e.paid_to}"
        out.append(
            (
                rules.BookEntry(f"cash:{e.id}", e.entry_date, e.amount, money_in, e.reference),
                label,
                _MODE_LABEL[e.mode],
            )
        )
    return out


def reconciliation(
    db: Session, date_from: date, date_to: date, account_id: int | None = None
) -> ReconciliationOut:
    if date_to < date_from:
        raise BusinessRuleError(
            "The end date is before the start date", code="BAD_RANGE", field="date_to"
        )
    window = get_settings_row(db).bank_match_days
    stmt = (
        select(BankStatementLine)
        .join(BankStatement, BankStatement.id == BankStatementLine.statement_id)
        .where(
            BankStatement.tenant_id == TENANT_ID,
            BankStatementLine.line_date >= date_from,
            BankStatementLine.line_date <= date_to,
        )
        .order_by(BankStatementLine.line_date, BankStatementLine.id)
    )
    if account_id is not None:
        stmt = stmt.where(BankStatement.bank_account_id == account_id)
    lines = list(db.scalars(stmt))
    books = books_in_range(db, date_from - timedelta(days=window), date_to + timedelta(days=window))
    info = {b.key: (label, mode) for b, label, mode in books}
    result = rules.match_statement(
        [
            rules.StatementLine(x.id, x.line_date, x.narration, x.reference, x.debit, x.credit)
            for x in lines
        ],
        [b for b, _, _ in books],
        window,
    )
    by_line = {m.line_id: m for m in result.matched}
    out_lines: list[BankLineOut] = []
    unmatched_in = unmatched_out = ZERO
    for x in lines:
        m = by_line.get(x.id)
        if m is None:
            unmatched_in += x.credit
            unmatched_out += x.debit
        out_lines.append(
            BankLineOut(
                id=x.id,
                line_date=x.line_date,
                narration=x.narration,
                reference=x.reference,
                debit=x.debit,
                credit=x.credit,
                matched=m is not None,
                matched_key=m.key if m else None,
                matched_label=info[m.key][0] if m else None,
                matched_how=m.how if m else None,
            )
        )
    # Book entries inside the range that no bank line took: recorded, but not in the bank.
    leftover = set(result.unmatched_books)
    not_in_bank = [
        BookEntryOut(
            key=b.key,
            entry_date=b.on,
            label=label,
            mode=mode,
            reference=b.reference,
            amount=b.amount,
            money_in=b.money_in,
        )
        for b, label, mode in books
        if b.key in leftover and date_from <= b.on <= date_to
    ]
    balance = db.execute(
        select(BankStatementLine.balance, BankStatementLine.line_date)
        .join(BankStatement, BankStatement.id == BankStatementLine.statement_id)
        .where(
            BankStatement.tenant_id == TENANT_ID,
            BankStatementLine.balance.is_not(None),
            BankStatementLine.line_date <= date_to,
        )
        .order_by(BankStatementLine.line_date.desc(), BankStatementLine.id.desc())
        .limit(1)
    ).first()
    return ReconciliationOut(
        date_from=date_from,
        date_to=date_to,
        window_days=window,
        lines=out_lines,
        line_count=len(lines),
        matched_count=len(result.matched),
        unmatched_count=len(result.unmatched_lines),
        unmatched_in=money(unmatched_in),
        unmatched_out=money(unmatched_out),
        not_in_bank=not_in_bank,
        not_in_bank_total=money(sum((n.amount for n in not_in_bank), ZERO)),
        last_balance=balance[0] if balance else None,
        last_balance_date=balance[1] if balance else None,
    )


def latest_balance(db: Session, on_or_before: date) -> tuple[Decimal, date] | None:
    """The newest balance printed on any statement, for the cash forecast (FM9)."""
    row = db.execute(
        select(BankStatementLine.balance, BankStatementLine.line_date)
        .where(
            BankStatementLine.tenant_id == TENANT_ID,
            BankStatementLine.balance.is_not(None),
            BankStatementLine.line_date <= on_or_before,
        )
        .order_by(BankStatementLine.line_date.desc(), BankStatementLine.id.desc())
        .limit(1)
    ).first()
    return (row[0], row[1]) if row and row[0] is not None else None
