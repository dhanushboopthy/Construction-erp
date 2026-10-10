"""Tally vouchers (FM4, docs/FINANCE_REVIEW.md F5). Pure functions: the documents are turned
into balanced double-entry vouchers and written as Tally's XML import format. Worked examples
are in tests/unit/test_tally.py.

Signs follow the books, not Tally's XML: an amount is positive for a debit and negative for a
credit, and every voucher must add to nothing, or it is refused. The XML writer translates to
Tally's convention (a debit has ISDEEMEDPOSITIVE Yes and a negative amount)."""

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from xml.sax.saxutils import escape

from app.domain.finance import CashEntryKind
from app.domain.money import ZERO, money


class Purpose(StrEnum):
    """The ledgers the export posts to. The accountant maps each to a name in their Tally."""

    SALES = "sales"
    PURCHASE = "purchase"
    OUTPUT_CGST = "output_cgst"
    OUTPUT_SGST = "output_sgst"
    OUTPUT_IGST = "output_igst"
    INPUT_CGST = "input_cgst"
    INPUT_SGST = "input_sgst"
    INPUT_IGST = "input_igst"
    ROUND_OFF = "round_off"
    CASH = "cash"
    BANK = "bank"
    DRAWINGS = "drawings"
    CAPITAL = "capital"
    REBATE = "rebate"
    FREIGHT = "freight"
    BAD_DEBT = "bad_debt"


# Sensible Tally defaults (accountant to confirm). Each: (ledger name, Tally group).
DEFAULTS: dict[Purpose, tuple[str, str]] = {
    Purpose.SALES: ("Sales", "Sales Accounts"),
    Purpose.PURCHASE: ("Purchases", "Purchase Accounts"),
    Purpose.OUTPUT_CGST: ("Output CGST", "Duties & Taxes"),
    Purpose.OUTPUT_SGST: ("Output SGST", "Duties & Taxes"),
    Purpose.OUTPUT_IGST: ("Output IGST", "Duties & Taxes"),
    Purpose.INPUT_CGST: ("Input CGST", "Duties & Taxes"),
    Purpose.INPUT_SGST: ("Input SGST", "Duties & Taxes"),
    Purpose.INPUT_IGST: ("Input IGST", "Duties & Taxes"),
    Purpose.ROUND_OFF: ("Round off", "Indirect Expenses"),
    Purpose.CASH: ("Cash", "Cash-in-Hand"),
    Purpose.BANK: ("Bank", "Bank Accounts"),
    Purpose.DRAWINGS: ("Owner's Drawings", "Capital Account"),
    Purpose.CAPITAL: ("Owner's Capital", "Capital Account"),
    Purpose.REBATE: ("Rebate Received", "Indirect Incomes"),
    Purpose.FREIGHT: ("Freight", "Direct Expenses"),
    Purpose.BAD_DEBT: ("Bad Debts Written Off", "Indirect Expenses"),
}
DEBTORS, CREDITORS, EXPENSES = "Sundry Debtors", "Sundry Creditors", "Indirect Expenses"

Names = Mapping[Purpose, str]


def ledger_names(overrides: Mapping[str, str]) -> dict[Purpose, str]:
    """Defaults, replaced by whatever names the accountant saved. A blank name keeps the default;
    names for purposes that do not exist are ignored."""
    names = {purpose: name for purpose, (name, _) in DEFAULTS.items()}
    for key, value in overrides.items():
        if key in Purpose._value2member_map_ and value.strip():
            names[Purpose(key)] = value.strip()
    return names


class VoucherKind(StrEnum):
    SALES = "Sales"
    PURCHASE = "Purchase"
    CREDIT_NOTE = "Credit Note"
    DEBIT_NOTE = "Debit Note"
    RECEIPT = "Receipt"
    PAYMENT = "Payment"
    CONTRA = "Contra"
    JOURNAL = "Journal"


class PartyAccount(StrEnum):
    RECEIVABLE = "receivable"  # a customer's account
    PAYABLE = "payable"  # a supplier's or transporter's account


@dataclass(frozen=True)
class Line:
    ledger: str
    amount: Decimal  # positive = debit, negative = credit
    purpose: Purpose | None = None  # which ledger purpose it is, whatever the ledger is called


class UnbalancedVoucherError(ValueError):
    pass


@dataclass(frozen=True)
class Voucher:
    kind: VoucherKind
    number: str
    on: date
    party: str | None  # the customer, supplier or transporter, when there is one
    narration: str
    lines: tuple[Line, ...]
    account: PartyAccount | None

    def __post_init__(self) -> None:
        if sum((line.amount for line in self.lines), ZERO) != ZERO:
            raise UnbalancedVoucherError(f"Voucher {self.number} does not balance")

    @property
    def party_effect(self) -> Decimal:
        """How much more the party owes us (receivable) or we owe the party (payable)."""
        if self.party is None or self.account is None:
            return ZERO
        net = sum((line.amount for line in self.lines if line.ledger == self.party), ZERO)
        return money(net if self.account is PartyAccount.RECEIVABLE else -net)

    @property
    def debit_total(self) -> Decimal:
        return money(sum((line.amount for line in self.lines if line.amount > ZERO), ZERO))


def _line(names: Names, purpose: Purpose, amount: Decimal) -> Line:
    return Line(names[purpose], amount, purpose)


def _keep(lines: Iterable[Line]) -> tuple[Line, ...]:
    return tuple(line for line in lines if line.amount != ZERO)


def tax_document(
    kind: VoucherKind,
    *,
    number: str,
    on: date,
    party: str,
    narration: str,
    grand: Decimal,
    taxable: Decimal,
    cgst: Decimal,
    sgst: Decimal,
    igst: Decimal,
    round_off: Decimal,
    names: Names,
    outward: bool,
    party_debit: bool,
) -> Voucher:
    """A bill or a note. `outward` is a sale (output tax, Sales ledger) or a purchase (input tax,
    Purchases ledger); `party_debit` says whether the party is debited (a bill we send, a note we
    send a supplier) or credited. Everything else is posted the other way."""
    heads = (
        (Purpose.OUTPUT_CGST, Purpose.OUTPUT_SGST, Purpose.OUTPUT_IGST)
        if outward
        else (Purpose.INPUT_CGST, Purpose.INPUT_SGST, Purpose.INPUT_IGST)
    )
    base = Purpose.SALES if outward else Purpose.PURCHASE
    sign = -1 if party_debit else 1
    lines = _keep(
        [
            Line(party, -sign * grand),
            _line(names, base, sign * taxable),
            _line(names, heads[0], sign * cgst),
            _line(names, heads[1], sign * sgst),
            _line(names, heads[2], sign * igst),
            _line(names, Purpose.ROUND_OFF, sign * round_off),
        ]
    )
    receivable = outward
    return Voucher(
        kind,
        number,
        on,
        party,
        narration,
        lines,
        PartyAccount.RECEIVABLE if receivable else PartyAccount.PAYABLE,
    )


def settlement(
    number: str,
    on: date,
    party: str,
    amount: Decimal,
    mode: str,
    *,
    received: bool,
    names: Names,
    narration: str = "",
) -> Voucher:
    """Money received from a customer (a Receipt) or paid to a supplier (a Payment). Cash goes
    to the Cash ledger; UPI and bank transfers go to Bank."""
    purpose = Purpose.CASH if mode == "cash" else Purpose.BANK
    sign = 1 if received else -1
    return Voucher(
        VoucherKind.RECEIPT if received else VoucherKind.PAYMENT,
        number,
        on,
        party,
        narration,
        (_line(names, purpose, sign * amount), Line(party, -sign * amount)),
        PartyAccount.RECEIVABLE if received else PartyAccount.PAYABLE,
    )


def cash_entry_voucher(
    kind: CashEntryKind,
    number: str,
    on: date,
    amount: Decimal,
    *,
    in_cash: bool,
    head: str,
    reversal: bool,
    narration: str,
    names: Names,
) -> Voucher:
    """A cash-book entry. `head` is the expense head's name. Deposits and withdrawals are contras
    between Cash and Bank. A reversal posts the original the other way round."""
    cash, bank = _line(names, Purpose.CASH, amount), _line(names, Purpose.BANK, amount)
    money_side = cash if in_cash else bank
    voucher_kind = VoucherKind.PAYMENT
    if kind is CashEntryKind.EXPENSE:
        debit, credit = Line(head, amount), money_side
    elif kind is CashEntryKind.BANK_DEPOSIT:
        debit, credit, voucher_kind = bank, cash, VoucherKind.CONTRA
    elif kind is CashEntryKind.BANK_WITHDRAWAL:
        debit, credit, voucher_kind = cash, bank, VoucherKind.CONTRA
    elif kind is CashEntryKind.OWNER_DRAWING:
        debit, credit = _line(names, Purpose.DRAWINGS, amount), money_side
    else:  # OWNER_CAPITAL
        debit = money_side
        credit, voucher_kind = _line(names, Purpose.CAPITAL, amount), VoucherKind.RECEIPT
    if reversal:
        debit, credit = credit, debit
    return Voucher(
        voucher_kind,
        number,
        on,
        None,
        narration,
        (
            Line(debit.ledger, amount, debit.purpose),
            Line(credit.ledger, -amount, credit.purpose),
        ),
        None,
    )


def journal(
    number: str,
    on: date,
    party: str,
    amount: Decimal,
    other: Purpose,
    *,
    names: Names,
    party_debit: bool,
    narration: str = "",
    account: PartyAccount = PartyAccount.PAYABLE,
) -> Voucher:
    """A supplier rebate, a freight payable or a bad debt written off: the party's account against
    an income or expense ledger."""
    sign = 1 if party_debit else -1
    return Voucher(
        VoucherKind.JOURNAL,
        number,
        on,
        party,
        narration,
        (Line(party, sign * amount), _line(names, other, -sign * amount)),
        account,
    )


def purpose_totals(vouchers: Iterable[Voucher]) -> dict[Purpose, Decimal]:
    """Net debit per ledger purpose over the vouchers, whatever the ledgers are called. Sales and
    output tax come out negative (credits); input tax and purchases positive."""
    out: dict[Purpose, Decimal] = defaultdict(lambda: ZERO)
    for v in vouchers:
        for line in v.lines:
            if line.purpose is not None:
                out[line.purpose] += line.amount
    return {purpose: money(total) for purpose, total in out.items()}


def whole_months(date_from: date, date_to: date) -> list[str] | None:
    """The calendar months ('2026-10') a range covers exactly, or None when it starts or ends
    part way through a month. GST returns exist only for whole months."""
    if date_from.day != 1 or date_to < date_from:
        return None
    if (date_to + timedelta(days=1)).day != 1:
        return None
    months: list[str] = []
    year, month = date_from.year, date_from.month
    while (year, month) <= (date_to.year, date_to.month):
        months.append(f"{year}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def totals_by_kind(vouchers: Iterable[Voucher]) -> dict[VoucherKind, tuple[int, Decimal]]:
    """How many vouchers of each kind, and the sum of their debits."""
    out: dict[VoucherKind, tuple[int, Decimal]] = defaultdict(lambda: (0, ZERO))
    for v in vouchers:
        count, total = out[v.kind]
        out[v.kind] = (count + 1, money(total + v.debit_total))
    return dict(out)


@dataclass(frozen=True)
class Master:
    """A ledger that must exist in Tally before a voucher can use it."""

    name: str
    parent: str  # the Tally group


def masters_for(
    names: Names,
    *,
    customers: Iterable[str],
    suppliers: Iterable[str],
    expense_heads: Iterable[str],
) -> list[Master]:
    found: dict[str, Master] = {}
    for purpose, (_, group) in DEFAULTS.items():
        found.setdefault(names[purpose], Master(names[purpose], group))
    for group, people in ((DEBTORS, customers), (CREDITORS, suppliers), (EXPENSES, expense_heads)):
        for name in people:
            found.setdefault(name, Master(name, group))
    return list(found.values())


_ILLEGAL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _text(value: str) -> str:
    """XML 1.0 cannot carry control characters; the rest is escaped."""
    return escape(_ILLEGAL.sub("", value))


def render_xml(company: str, vouchers: Iterable[Voucher], masters: Iterable[Master]) -> str:
    """Tally's Import Data envelope: ledger masters first, then the vouchers. Every voucher has
    a GUID built from its type and number, so importing the same file twice creates nothing new."""
    messages: list[str] = []
    for m in masters:
        messages.append(
            '<TALLYMESSAGE xmlns:UDF="TallyUDF">'
            f'<LEDGER NAME="{_text(m.name)}" ACTION="Create">'
            f"<NAME>{_text(m.name)}</NAME><PARENT>{_text(m.parent)}</PARENT>"
            "</LEDGER></TALLYMESSAGE>"
        )
    for v in vouchers:
        entries = "".join(
            "<ALLLEDGERENTRIES.LIST>"
            f"<LEDGERNAME>{_text(line.ledger)}</LEDGERNAME>"
            f"<ISDEEMEDPOSITIVE>{'Yes' if line.amount > ZERO else 'No'}</ISDEEMEDPOSITIVE>"
            f"<AMOUNT>{-line.amount:.2f}</AMOUNT>"
            "</ALLLEDGERENTRIES.LIST>"
            for line in v.lines
        )
        party = f"<PARTYLEDGERNAME>{_text(v.party)}</PARTYLEDGERNAME>" if v.party else ""
        messages.append(
            '<TALLYMESSAGE xmlns:UDF="TallyUDF">'
            f'<VOUCHER VCHTYPE="{v.kind.value}" ACTION="Create" OBJVIEW="Accounting Voucher View">'
            f"<DATE>{v.on:%Y%m%d}</DATE>"
            f"<GUID>{_text(f'ERP-{v.kind.value}-{v.number}')}</GUID>"
            f"<VOUCHERTYPENAME>{v.kind.value}</VOUCHERTYPENAME>"
            f"<VOUCHERNUMBER>{_text(v.number)}</VOUCHERNUMBER>"
            f"{party}"
            f"<NARRATION>{_text(v.narration)}</NARRATION>"
            f"{entries}"
            "</VOUCHER></TALLYMESSAGE>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Import Data</TALLYREQUEST>"
        "<TYPE>Data</TYPE><ID>All Masters</ID></HEADER><BODY><IMPORTDATA><REQUESTDESC>"
        "<REPORTNAME>All Masters</REPORTNAME><STATICVARIABLES>"
        f"<SVCURRENTCOMPANY>{_text(company)}</SVCURRENTCOMPANY>"
        "</STATICVARIABLES></REQUESTDESC><REQUESTDATA>"
        f"{''.join(messages)}"
        "</REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>"
    )
