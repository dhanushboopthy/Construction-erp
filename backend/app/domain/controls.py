"""Controls (FM7, docs/FINANCE_REVIEW.md F16 to F18): the period lock, reading a bank statement
CSV, matching it to the books, and the rules behind the owner's exception report. Pure functions;
worked examples are in tests/unit/test_controls.py."""

import csv
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from app.domain.money import ZERO, Numberish, money, to_decimal

# ---------------------------------------------------------------------------- period lock


def is_locked(on: date, locked_through: date | None) -> bool:
    """A document dated on or before the lock date is refused (F18)."""
    return locked_through is not None and on <= locked_through


def reopens(new: date | None, old: date | None) -> bool:
    """Moving the lock earlier, or removing it, lets old months change again: the owner gives a
    reason and it is audited."""
    if old is None:
        return False
    return new is None or new < old


# ---------------------------------------------------------------------------- bank statement


@dataclass(frozen=True)
class BankRow:
    """One line of a bank statement. Debit is money out of the bank, credit is money in."""

    line_no: int  # line in the file, for error messages
    on: date
    narration: str
    reference: str
    debit: Decimal
    credit: Decimal
    balance: Decimal | None


@dataclass(frozen=True)
class ParsedStatement:
    rows: list[BankRow]
    errors: list[str]  # when there are errors, rows is empty: nothing is half imported


_HEADERS: dict[str, set[str]] = {
    "date": {"date", "txndate", "transactiondate", "trandate", "valuedate", "postingdate"},
    "narration": {
        "narration",
        "description",
        "particulars",
        "remarks",
        "transactionremarks",
        "details",
    },
    "reference": {"reference", "refno", "chqrefno", "chequeno", "ref", "utr", "chqno", "chequeref"},
    "debit": {"debit", "withdrawal", "withdrawalamt", "dr", "debitamount", "withdrawals"},
    "credit": {"credit", "deposit", "depositamt", "cr", "creditamount", "deposits"},
    "balance": {"balance", "closingbalance", "runningbalance"},
}
_DATE_FORMATS = ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y", "%Y-%m-%d", "%d-%b-%Y", "%d %b %Y")


def _key(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", header.lower())


def _column_map(header: list[str]) -> dict[str, int]:
    found: dict[str, int] = {}
    for i, cell in enumerate(header):
        k = _key(cell)
        for field, names in _HEADERS.items():
            if k in names and field not in found:
                found[field] = i
    return found


def _read_date(text: str) -> date | None:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text.strip(), fmt).date()  # noqa: DTZ007 - a calendar date
        except ValueError:
            continue
    return None


def _read_amount(text: str) -> Decimal:
    cleaned = re.sub(r"[,\s₹]", "", text)
    if cleaned == "":
        return ZERO
    try:
        return money(Decimal(cleaned))
    except InvalidOperation as exc:
        raise ValueError(text) from exc


def parse_bank_csv(text: str) -> ParsedStatement:
    """Read a bank's CSV. The header row is found by its column names (date, narration,
    reference, debit or withdrawal, credit or deposit, balance), so the layouts of different
    banks work and extra columns are ignored. Any bad row refuses the whole file."""
    table = list(csv.reader(text.splitlines()))
    if not any(any(cell.strip() for cell in r) for r in table):
        return ParsedStatement([], ["The file is empty."])
    header_at = None
    columns: dict[str, int] = {}
    for i, r in enumerate(table):
        mapped = _column_map(r)
        if "date" in mapped and ("debit" in mapped or "credit" in mapped):
            header_at, columns = i, mapped
            break
    if header_at is None:
        guess = _column_map(table[0]) if table else {}
        if "date" not in guess:
            return ParsedStatement([], ["There is no Date column in the file."])
        return ParsedStatement([], ["There is no Debit or Credit amount column in the file."])

    def cell(r: list[str], field: str) -> str:
        i = columns.get(field)
        return r[i].strip() if i is not None and i < len(r) else ""

    rows: list[BankRow] = []
    errors: list[str] = []
    for n, r in enumerate(table[header_at + 1 :], start=header_at + 2):
        if not any(c.strip() for c in r):
            continue
        on = _read_date(cell(r, "date"))
        if on is None:
            errors.append(f"Line {n}: '{cell(r, 'date')}' is not a date.")
            continue
        try:
            debit = _read_amount(cell(r, "debit"))
            credit = _read_amount(cell(r, "credit"))
            balance_text = cell(r, "balance")
            balance = _read_amount(balance_text) if balance_text else None
        except ValueError as exc:
            errors.append(f"Line {n}: '{exc.args[0]}' is not an amount.")
            continue
        if debit < ZERO or credit < ZERO:
            errors.append(f"Line {n}: a negative amount. Debits and credits are positive.")
        elif debit > ZERO and credit > ZERO:
            errors.append(f"Line {n}: both a debit and a credit on one row.")
        elif debit == ZERO and credit == ZERO:
            errors.append(f"Line {n}: no amount.")
        else:
            rows.append(
                BankRow(n, on, cell(r, "narration"), cell(r, "reference"), debit, credit, balance)
            )
    if errors:
        return ParsedStatement([], errors)
    return ParsedStatement(rows, [])


# ---------------------------------------------------------------------------- matching


@dataclass(frozen=True)
class StatementLine:
    id: int
    on: date
    narration: str
    reference: str
    debit: Decimal
    credit: Decimal

    @property
    def money_in(self) -> bool:
        return self.credit > ZERO

    @property
    def amount(self) -> Decimal:
        return self.credit if self.money_in else self.debit


@dataclass(frozen=True)
class BookEntry:
    """A receipt, supplier payment, deposit or withdrawal the shop recorded, to look for in the
    bank."""

    key: str
    on: date
    amount: Decimal
    money_in: bool  # into the bank
    reference: str | None = None


@dataclass(frozen=True)
class Match:
    line_id: int
    key: str
    how: str  # "reference" or "amount"
    days_apart: int


@dataclass(frozen=True)
class MatchResult:
    matched: list[Match]
    unmatched_lines: list[int]
    unmatched_books: list[str]


MIN_REFERENCE = 4  # a shorter reference ("12") is too likely to appear by chance


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _ref_hit(line: StatementLine, entry: BookEntry) -> bool:
    ref = _norm(entry.reference or "")
    if len(ref) < MIN_REFERENCE:
        return False
    return ref in _norm(line.narration) or ref in _norm(line.reference)


def match_statement(
    lines: list[StatementLine], books: list[BookEntry], window_days: int
) -> MatchResult:
    """Pair each bank line with at most one book entry of the same direction and amount, dated
    within `window_days`. A matching reference wins over date; otherwise the nearest date wins.
    References are paired first so an amount-only match cannot take their partner."""
    ordered = sorted(lines, key=lambda x: (x.on, x.id))
    free = sorted(books, key=lambda b: (b.on, b.key))
    taken_books: set[str] = set()
    matched: dict[int, Match] = {}

    def candidates(line: StatementLine) -> list[BookEntry]:
        return [
            b
            for b in free
            if b.key not in taken_books
            and b.money_in == line.money_in
            and b.amount == line.amount
            and abs((b.on - line.on).days) <= window_days
        ]

    for use_reference in (True, False):
        for line in ordered:
            if line.id in matched:
                continue
            options = candidates(line)
            if use_reference:
                options = [b for b in options if _ref_hit(line, b)]
            if not options:
                continue
            best = min(options, key=lambda b: (abs((b.on - line.on).days), b.on, b.key))
            taken_books.add(best.key)
            matched[line.id] = Match(
                line.id,
                best.key,
                "reference" if use_reference else "amount",
                abs((best.on - line.on).days),
            )
    return MatchResult(
        matched=[matched[x.id] for x in ordered if x.id in matched],
        unmatched_lines=[x.id for x in ordered if x.id not in matched],
        unmatched_books=[b.key for b in free if b.key not in taken_books],
    )


# ---------------------------------------------------------------------------- exception rules


def is_round(amount: Numberish, step: Numberish) -> bool:
    """A value that is a whole number of `step` rupees and at least one step. Made-up entries
    tend to be round; real stock at average cost rarely is. A zero step switches the rule off."""
    value, unit = to_decimal(amount), to_decimal(step)
    return unit > ZERO and value >= unit and value % unit == ZERO


def repeated_within(dates: list[date], count: int, days: int) -> tuple[date, date, int] | None:
    """The first run of at least `count` events inside `days` calendar days (first and last day
    included): (first date, last date, events in the run). None when there is none, or when
    `count` is zero (rule off)."""
    if count <= 0 or days <= 0:
        return None
    ordered = sorted(dates)
    for i, start in enumerate(ordered):
        window = [d for d in ordered[i:] if d < start + timedelta(days=days)]
        if len(window) >= count:
            return start, window[-1], len(window)
    return None


def days_before(on: date, target: date, within: int) -> int | None:
    """How many days `on` is before `target` (0 for the same day), or None when it is after the
    target or more than `within` days before it."""
    gap = (target - on).days
    return gap if 0 <= gap <= within else None


def near_limit(amount: Numberish, limit: Numberish, pct: Numberish) -> bool:
    """The amount is at least `pct` % of the limit. No limit, or a zero percentage, is off."""
    cap, share = to_decimal(limit), to_decimal(pct)
    if cap <= ZERO or share <= ZERO:
        return False
    return to_decimal(amount) >= cap * share / Decimal(100)


def backdated_days(doc_date: date, entered_on: date) -> int:
    """Days between the date on a document and the day it was keyed in, when it was dated
    earlier; zero otherwise."""
    return max((entered_on - doc_date).days, 0)
