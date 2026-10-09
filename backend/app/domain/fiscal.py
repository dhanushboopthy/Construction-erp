"""Financial year (April to March by default) and document number formatting."""

import re
from datetime import date

# CGST Rules, rule 46(b): the invoice serial number may not exceed 16 characters.
DOC_NUMBER_MAX_LENGTH = 16
SEQUENCE_WIDTH = 5
_SERIES = re.compile(r"[A-Z0-9]{1,6}")


def fy_start_year(on: date, start_month: int = 4) -> int:
    if not 1 <= start_month <= 12:
        raise ValueError("start_month must be 1-12")
    return on.year if on.month >= start_month else on.year - 1


def fy_label(on: date, start_month: int = 4) -> str:
    """Short label used inside document numbers, e.g. '26-27' for 1 Oct 2026."""
    start = fy_start_year(on, start_month)
    if start_month == 1:
        return f"{start % 100:02d}"
    return f"{start % 100:02d}-{(start + 1) % 100:02d}"


def fy_bounds(on: date, start_month: int = 4) -> tuple[date, date]:
    """First and last day of the financial year containing `on`."""
    start_year = fy_start_year(on, start_month)
    first = date(start_year, start_month, 1)
    next_first = date(start_year + 1, start_month, 1)
    return first, date.fromordinal(next_first.toordinal() - 1)


def format_doc_number(series: str, fy: str, sequence: int) -> str:
    """Build e.g. 'S1/26-27/00042'. Raises if the result would break the 16-character limit."""
    if sequence < 1:
        raise ValueError("sequence starts at 1")
    if not _SERIES.fullmatch(series):
        raise ValueError("series must be uppercase letters and digits")
    number = f"{series}/{fy}/{sequence:0{SEQUENCE_WIDTH}d}"
    if len(number) > DOC_NUMBER_MAX_LENGTH:
        raise ValueError(f"document number {number!r} exceeds {DOC_NUMBER_MAX_LENGTH} characters")
    return number


def fy_months(start_year: int, start_month: int = 4) -> list[tuple[int, int]]:
    """The twelve (year, month) pairs of the financial year that starts in `start_year`."""
    return [
        (start_year + (start_month - 1 + i) // 12, (start_month - 1 + i) % 12 + 1)
        for i in range(12)
    ]
