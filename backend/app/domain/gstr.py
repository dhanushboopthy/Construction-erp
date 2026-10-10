"""GST return rules (Milestone 13): which GSTR-1 table a bill belongs to, document series,
quantity codes, and matching our purchases against the portal's GSTR-2B. Pure maths; the
thresholds are confirmed with the accountant (docs/GAP_ANALYSIS.md)."""

import calendar
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.money import ZERO, Numberish, money, to_decimal

# An inter-state bill to an unregistered buyer above this is listed bill by bill (B2CL).
B2CL_THRESHOLD = Decimal("100000")

_UQC = {
    "kg": "KGS",
    "kgs": "KGS",
    "bag": "BAG",
    "bags": "BAG",
    "piece": "PCS",
    "pieces": "PCS",
    "pc": "PCS",
    "pcs": "PCS",
    "nos": "NOS",
    "bundle": "BDL",
    "bdl": "BDL",
    "metre": "MTR",
    "meter": "MTR",
    "mtr": "MTR",
    "m": "MTR",
    "ton": "TON",
    "tons": "TON",
    "tonne": "TON",
}
_NUMBER = re.compile(r"^(?P<series>.+)/(?P<seq>[0-9]+)$")
_PERIOD = re.compile(r"^(?P<y>[0-9]{4})-(?P<m>0[1-9]|1[0-2])$")


def is_b2cl(registered: bool, inter_state: bool, invoice_value: Numberish) -> bool:
    return (not registered) and inter_state and money(invoice_value) > B2CL_THRESHOLD


def uqc(unit: str) -> str:
    """GST unit quantity code for an item's base unit; OTH when there is no better match."""
    return _UQC.get(unit.strip().lower(), "OTH")


def parse_period(text: str) -> tuple[int, int]:
    found = _PERIOD.match(text or "")
    if not found:
        raise ValueError("period must look like 2026-10")
    return int(found["y"]), int(found["m"])


def period_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def filing_period(year: int, month: int) -> str:
    """The portal's 'fp' value: MMYYYY."""
    return f"{month:02d}{year:04d}"


@dataclass(frozen=True)
class SeriesSummary:
    series: str
    first: str
    last: str
    count: int
    gaps: list[int]  # sequence numbers missing between first and last (should always be empty)


def document_series(numbers: list[str]) -> list[SeriesSummary]:
    """Group document numbers by series (all before the sequence) for the document summary."""
    groups: dict[str, dict[int, str]] = defaultdict(dict)
    for number in numbers:
        found = _NUMBER.match(number)
        if not found:
            raise ValueError(f"not a document number: {number!r}")
        groups[found["series"]][int(found["seq"])] = number
    out: list[SeriesSummary] = []
    for series in sorted(groups):
        seqs = groups[series]
        low, high = min(seqs), max(seqs)
        out.append(
            SeriesSummary(
                series=series,
                first=seqs[low],
                last=seqs[high],
                count=len(seqs),
                gaps=[n for n in range(low, high + 1) if n not in seqs],
            )
        )
    return out


def normalize_doc_no(number: str) -> str:
    """Compare supplier bill numbers loosely: ignore case, spaces and punctuation."""
    return re.sub(r"[^A-Z0-9]", "", number.upper())


@dataclass(frozen=True)
class BillFigures:
    gstin: str
    number: str
    taxable: Decimal
    igst: Decimal
    cgst: Decimal
    sgst: Decimal

    @property
    def tax(self) -> Decimal:
        return self.igst + self.cgst + self.sgst


@dataclass(frozen=True)
class Match:
    gstin: str
    number: str
    status: str  # matched | mismatch | missing_in_2b | missing_in_books
    books: BillFigures | None
    portal: BillFigures | None
    difference_taxable: Decimal  # portal less books
    difference_tax: Decimal


def reconcile(
    books: list[BillFigures], portal: list[BillFigures], tolerance: Numberish
) -> list[Match]:
    """Match purchase bills to GSTR-2B rows by supplier GSTIN and bill number.

    Amounts within `tolerance` rupees count as the same (suppliers round differently). A bill
    listed twice in the books matches only once."""
    limit = to_decimal(tolerance)

    def key(b: BillFigures) -> tuple[str, str]:
        return (b.gstin.strip().upper(), normalize_doc_no(b.number))

    waiting: dict[tuple[str, str], list[BillFigures]] = defaultdict(list)
    for row in books:
        waiting[key(row)].append(row)
    out: list[Match] = []
    for row in portal:
        mine = waiting[key(row)].pop(0) if waiting[key(row)] else None
        if mine is None:
            out.append(
                Match(row.gstin, row.number, "missing_in_books", None, row, row.taxable, row.tax)
            )
            continue
        d_taxable, d_tax = money(row.taxable - mine.taxable), money(row.tax - mine.tax)
        same = abs(d_taxable) <= limit and abs(d_tax) <= limit
        out.append(
            Match(
                mine.gstin,
                mine.number,
                "matched" if same else "mismatch",
                mine,
                row,
                d_taxable,
                d_tax,
            )
        )
    for rows in waiting.values():
        for row in rows:
            out.append(
                Match(row.gstin, row.number, "missing_in_2b", row, None, -row.taxable, -row.tax)
            )
    return out


# ---------------------------------------------------------------------------- ITC at risk (FM8)


def mismatch_itc_at_risk(books_tax: Numberish, portal_tax: Numberish) -> Decimal:
    """Input tax we booked that the supplier's return does not support: books less 2B, never
    below zero (the portal showing more than the books is not a risk to us)."""
    return money(max(to_decimal(books_tax) - to_decimal(portal_tax), ZERO))


def payable_if_unclaimed(payable: Numberish, at_risk: Numberish) -> Decimal:
    """GST to pay if the at-risk input tax cannot be claimed: it comes back onto the payable."""
    return money(to_decimal(payable) + to_decimal(at_risk))
