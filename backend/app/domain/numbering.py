"""Document numbering rules for the admin (Milestone 26, ADR 0013).

Two numbers describe a series. The *highest existing number* is read from the documents
themselves (a cancelled bill counts, a deleted one does not) and is the only thing that may
refuse a value. The *configured next number* is the counter's high-water mark; it is what the next
document will be called. Pure: no database, no clock.
"""

import re
from collections.abc import Iterable, Sequence

from app.domain.fiscal import format_doc_number

MAX_NEXT = 99_999
MAX_REASON = 300
_NUMBER = re.compile(r"^([A-Z0-9]+)/(\d\d(?:-\d\d)?)/(\d+)$")

_LABELS = {
    "sales_invoice": "Bill",
    "credit_note": "Credit note",
    "debit_note": "Debit note",
    "delivery_challan": "Delivery challan",
    "purchase_entry": "Purchase",
    "payment_receipt": "Receipt",
    "cash_voucher": "Cash voucher",
    "stock_adjustment": "Stock adjustment",
    "bad_debt_writeoff": "Bad-debt write-off",
    "stock_writedown": "Stock write-down",
    "purchase_order": "Purchase order",
    "goods_receipt": "Goods receipt",
    "quotation": "Quotation",
    "proforma": "Proforma invoice",
}


class NumberingError(ValueError):
    """A value the series cannot take. The message is shown to the admin as it is."""


def label_of(doc_type: str) -> str:
    return _LABELS.get(doc_type, "Document")


def parse_number(number: str) -> tuple[str, str, int] | None:
    """('MAIN', '26-27', 25) for 'MAIN/26-27/00025'; None when it is not a document number."""
    found = _NUMBER.match(number)
    return (found[1], found[2], int(found[3])) if found else None


def floor_for(highest: int | None) -> int:
    """The lowest next number a series may be set to."""
    return 1 if highest is None else highest + 1


def check_next(
    next_number: int, highest: int | None, highest_text: str | None, doc_type: str
) -> None:
    if next_number < 1:
        raise NumberingError("The next number must be at least 1.")
    if next_number > MAX_NEXT:
        raise NumberingError(f"The next number cannot be more than {MAX_NEXT}.")
    floor = floor_for(highest)
    if next_number < floor:
        raise NumberingError(
            f"{label_of(doc_type)} {highest_text} already exists. "
            f"The next number must be {floor} or higher."
        )


def next_document(prefix: str, financial_year: str, sequence: int) -> str:
    return format_doc_number(prefix, financial_year, sequence)


def is_ahead(configured: int, highest: int | None) -> bool:
    """The counter is ahead of its documents: the next one will leave a gap."""
    return configured > floor_for(highest)


def suggested_next(configured: int, highest: int | None) -> int | None:
    """The value that closes the gap, when there is one."""
    return floor_for(highest) if is_ahead(configured, highest) else None


def clean_reason(reason: str | None) -> str:
    text = (reason or "").strip()
    if not text:
        raise NumberingError("Give a reason for the change.")
    if len(text) > MAX_REASON:
        raise NumberingError(f"The reason is too long (at most {MAX_REASON} characters).")
    return text


def skipped(from_value: int, to_value: int, floor: int) -> range:
    """The numbers an audited change left unused: from the lower of the old counter and the
    floor, up to (not including) the new next number. A move down skips nothing."""
    return range(min(from_value, floor), to_value)


def unexplained_gaps(gaps: Iterable[int], explained: Sequence[range]) -> list[int]:
    return [g for g in gaps if not any(g in r for r in explained)]
