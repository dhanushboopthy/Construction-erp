"""Party ledger maths (Milestones 3 and 7): balances, open items and aging.

The ledger is append-only. A customer's account is `receivable` (bills are debits, payments
and credit notes are credits); a supplier's is `payable` (bills are credits, payments are
debits). Payments clear the oldest bill first (SPEC section 5.6); money paid beyond the bills
stays as an advance and is used by the next bill (G21).
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum

from app.domain.money import ZERO, money


class Account(StrEnum):
    RECEIVABLE = "receivable"  # customers owe us
    PAYABLE = "payable"  # we owe suppliers


@dataclass(frozen=True)
class LedgerEntry:
    entry_date: date
    debit: Decimal
    credit: Decimal
    ref: str = ""
    # A payment aimed at one bill (by its number). Blank means oldest bill first.
    applies_to: str | None = None


@dataclass(frozen=True)
class OpenItem:
    ref: str
    entry_date: date
    original: Decimal
    remaining: Decimal


@dataclass(frozen=True)
class OpenItems:
    items: list[OpenItem] = field(default_factory=list)
    advance: Decimal = ZERO


@dataclass(frozen=True)
class Aging:
    up_to_30: Decimal
    days_31_60: Decimal
    over_60: Decimal

    @property
    def total(self) -> Decimal:
        return self.up_to_30 + self.days_31_60 + self.over_60


def _increase(entry: LedgerEntry, account: Account) -> Decimal:
    return entry.debit if account is Account.RECEIVABLE else entry.credit


def _decrease(entry: LedgerEntry, account: Account) -> Decimal:
    return entry.credit if account is Account.RECEIVABLE else entry.debit


def balance(entries: list[LedgerEntry], account: Account) -> Decimal:
    """What is owed on the account. Negative means we hold the other party's advance."""
    total = sum((_increase(e, account) - _decrease(e, account) for e in entries), ZERO)
    return money(total)


def open_items(entries: list[LedgerEntry], account: Account) -> OpenItems:
    """Unpaid bills after applying payments oldest-first, plus any unused advance.

    Entries are processed by date; entries of the same date keep the order they were given."""
    ordered = sorted(enumerate(entries), key=lambda pair: (pair[1].entry_date, pair[0]))
    queue: list[OpenItem] = []
    advance = ZERO
    for _, entry in ordered:
        bill = _increase(entry, account)
        if bill > ZERO:
            used = min(advance, bill)
            advance -= used
            if bill - used > ZERO:
                queue.append(OpenItem(entry.ref, entry.entry_date, money(bill), money(bill - used)))
        payment = _decrease(entry, account)
        if payment > ZERO and entry.applies_to:
            for position, head in enumerate(queue):
                if head.ref == entry.applies_to:
                    applied = min(head.remaining, payment)
                    payment -= applied
                    if applied == head.remaining:
                        queue.pop(position)
                    else:
                        queue[position] = OpenItem(
                            head.ref, head.entry_date, head.original, head.remaining - applied
                        )
                    break
        while payment > ZERO and queue:
            head = queue[0]
            applied = min(head.remaining, payment)
            payment -= applied
            if applied == head.remaining:
                queue.pop(0)
            else:
                queue[0] = OpenItem(
                    head.ref, head.entry_date, head.original, head.remaining - applied
                )
        advance += payment
    return OpenItems(items=queue, advance=money(advance))


def aging(result: OpenItems, today: date) -> Aging:
    """Unpaid amounts by days since the bill: 0-30, 31-60 and over 60."""
    buckets = [ZERO, ZERO, ZERO]
    for item in result.items:
        days = max((today - item.entry_date).days, 0)
        buckets[0 if days <= 30 else 1 if days <= 60 else 2] += item.remaining
    return Aging(money(buckets[0]), money(buckets[1]), money(buckets[2]))


@dataclass(frozen=True)
class Allocation:
    applied: list[tuple[str, Decimal]]  # (bill number, amount) in the order they were paid
    advance: Decimal  # money left over, held on the account (G21)


def allocate(
    opened: OpenItems, amount: Decimal, picks: dict[str, Decimal] | None = None
) -> Allocation:
    """Split a payment over open bills: the bills the user picked first, then oldest first,
    and any money left after every bill is paid is an advance (G21).

    Raises ValueError if a pick is not open, is more than the bill's balance, or the picks add
    up to more than the payment."""
    if amount <= ZERO:
        raise ValueError("a payment must be positive")
    remaining = {i.ref: i.remaining for i in opened.items}
    paid: dict[str, Decimal] = {}
    left = amount
    for ref, pick in (picks or {}).items():
        if pick <= ZERO:
            raise ValueError("each picked amount must be positive")
        if ref not in remaining:
            raise ValueError(f"bill {ref} is not open")
        if pick > remaining[ref]:
            raise ValueError(f"{pick} is more than the {remaining[ref]} still open on {ref}")
        if pick > left:
            raise ValueError("the picked amounts exceed the payment")
        paid[ref] = paid.get(ref, ZERO) + pick
        remaining[ref] -= pick
        left -= pick
    # What is not aimed at a bill goes oldest first, exactly as the ledger will replay it.
    for item in opened.items:
        take = min(remaining[item.ref], left)
        if take > ZERO:
            paid[item.ref] = paid.get(item.ref, ZERO) + take
            left -= take
    return Allocation(applied=[(ref, money(v)) for ref, v in paid.items()], advance=money(left))
