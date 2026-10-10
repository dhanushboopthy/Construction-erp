"""Controls (FM7): the period lock, reading a bank statement, matching it to the books and the
rules behind the owner's exception report. Hand-worked numbers.

Bank statement of 10 rows (October). 8 are UPI or bank receipts the shop recorded, 2 are not:
  1  03-10  UPI/RAVI/412345678901      credit  25,000.00   -> receipt R1, reference 412345678901
  2  03-10  NEFT SHARMA TRADERS        credit  50,000.00   -> receipt R2 (no reference)
  3  04-10  UPI/SURESH/412345678902    credit  12,400.00   -> receipt R3, reference 412345678902
  4  05-10  CASH DEPOSIT S1            credit 1,50,000.00  -> cash deposit D1 (cash book)
  5  06-10  UPI/RAVI/412345678903      credit  25,000.00   -> receipt R4, reference 412345678903
  6  07-10  NEFT SUPPLIER STEEL CO     debit  3,00,000.00  -> supplier payment P1
  7  08-10  UPI/MOHAN/412345678904     credit   9,900.00   -> receipt R5, reference 412345678904
  8  09-10  CHQ DEP UNKNOWN            credit  18,750.00   -> nothing in the books (unmatched)
  9  10-10  UPI/ANIL/412345678905      credit   7,500.00   -> receipt R6, reference 412345678905
 10  11-10  BANK CHARGES                debit      590.00   -> nothing in the books (unmatched)
Books also hold a ₹8,000 UPI receipt (R7) that never reached the bank: the "fake or failed UPI"
case. 8 lines match, 2 lines and 1 book entry are left over.

Round numbers: with a step of ₹1,000, ₹10,000 and ₹1,000 are round, ₹10,500 and ₹760 are not.
Returns: 4 credit notes to one customer on 02-10, 09-10, 15-10 and 28-10 are inside 30 days
(28-10 minus 02-10 is 26 days); 5 on 01-10, 10-10, 25-10, 03-11 are not.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.domain import controls as c

D = Decimal

CSV = """Account Statement,,,,,,
Date,Narration,Chq./Ref.No.,Value Dt,Withdrawal Amt.,Deposit Amt.,Closing Balance
03/10/26,UPI/RAVI/412345678901,412345678901,03/10/26,,"25,000.00","5,25,000.00"
03/10/26,NEFT SHARMA TRADERS,,03/10/26,,50000.00,575000.00
04/10/26,UPI/SURESH/412345678902,412345678902,04/10/26,,12400.00,587400.00
05/10/26,CASH DEPOSIT S1,,05/10/26,,150000.00,737400.00
06/10/26,UPI/RAVI/412345678903,412345678903,06/10/26,,25000.00,762400.00
07/10/26,NEFT SUPPLIER STEEL CO,,07/10/26,300000.00,,462400.00
08/10/26,UPI/MOHAN/412345678904,412345678904,08/10/26,,9900.00,472300.00
09/10/26,CHQ DEP UNKNOWN,,09/10/26,,18750.00,491050.00
10/10/26,UPI/ANIL/412345678905,412345678905,10/10/26,,7500.00,498550.00
11/10/26,BANK CHARGES,,11/10/26,590.00,,497960.00
"""


def test_parse_reads_ten_rows_and_ignores_extra_columns() -> None:
    parsed = c.parse_bank_csv(CSV)
    assert parsed.errors == []
    assert len(parsed.rows) == 10
    first = parsed.rows[0]
    assert first.on == date(2026, 10, 3)
    assert first.credit == D("25000.00") and first.debit == D("0.00")
    assert first.reference == "412345678901"
    assert first.balance == D("525000.00")
    assert parsed.rows[5].debit == D("300000.00")  # the supplier payment
    assert parsed.rows[9].narration == "BANK CHARGES"


def test_parse_accepts_other_headers_and_date_formats() -> None:
    text = "Txn Date,Description,Ref No,Debit,Credit\n2026-10-03,UPI IN,ABCD1234,,1500\n"
    parsed = c.parse_bank_csv(text)
    assert parsed.errors == []
    assert parsed.rows[0].on == date(2026, 10, 3)
    assert parsed.rows[0].credit == D("1500.00")
    assert parsed.rows[0].balance is None
    text2 = "Date,Narration,Debit,Credit\n03-Oct-2026,X,200,\n"
    assert c.parse_bank_csv(text2).rows[0].debit == D("200.00")


def test_parse_lists_every_bad_row_with_its_line_number() -> None:
    text = (
        "Date,Narration,Debit,Credit\n"
        "31/02/2026,Bad date,,100\n"
        "03/10/2026,Both,10,20\n"
        "03/10/2026,Nothing,,\n"
        "03/10/2026,Words,abc,\n"
    )
    parsed = c.parse_bank_csv(text)
    assert parsed.rows == []
    assert len(parsed.errors) == 4
    assert parsed.errors[0].startswith("Line 2:")
    assert "both" in parsed.errors[1].lower()
    assert "no amount" in parsed.errors[2].lower()
    assert "abc" in parsed.errors[3]


def test_parse_refuses_a_file_without_the_needed_columns() -> None:
    parsed = c.parse_bank_csv("Foo,Bar\n1,2\n")
    assert parsed.rows == [] and "Date" in parsed.errors[0]
    only_debit = c.parse_bank_csv("Date,Narration\n03/10/2026,x\n")
    assert only_debit.errors and "amount" in only_debit.errors[0].lower()
    assert c.parse_bank_csv("").errors == ["The file is empty."]


def test_parse_skips_blank_rows() -> None:
    text = "Date,Narration,Debit,Credit\n\n03/10/2026,ok,,100\n,,,\n"
    parsed = c.parse_bank_csv(text)
    assert parsed.errors == [] and len(parsed.rows) == 1


def test_parse_refuses_negative_amounts_and_saves_nothing() -> None:
    text = "Date,Narration,Debit,Credit\n03/10/2026,ok,,100\n04/10/2026,neg,-5,\n"
    parsed = c.parse_bank_csv(text)
    assert parsed.rows == []
    assert any("negative" in e.lower() for e in parsed.errors)


def line(i: int, on: date, narration: str, credit: str = "0", debit: str = "0") -> c.StatementLine:
    return c.StatementLine(
        id=i, on=on, narration=narration, reference="", debit=D(debit), credit=D(credit)
    )


def book(key: str, on: date, amount: str, money_in: bool, ref: str | None = None) -> c.BookEntry:
    return c.BookEntry(key=key, on=on, amount=D(amount), money_in=money_in, reference=ref)


def october() -> tuple[list[c.StatementLine], list[c.BookEntry]]:
    d = lambda n: date(2026, 10, n)  # noqa: E731
    lines = [
        line(1, d(3), "UPI/RAVI/412345678901", "25000"),
        line(2, d(3), "NEFT SHARMA TRADERS", "50000"),
        line(3, d(4), "UPI/SURESH/412345678902", "12400"),
        line(4, d(5), "CASH DEPOSIT S1", "150000"),
        line(5, d(6), "UPI/RAVI/412345678903", "25000"),
        line(6, d(7), "NEFT SUPPLIER STEEL CO", debit="300000"),
        line(7, d(8), "UPI/MOHAN/412345678904", "9900"),
        line(8, d(9), "CHQ DEP UNKNOWN", "18750"),
        line(9, d(10), "UPI/ANIL/412345678905", "7500"),
        line(10, d(11), "BANK CHARGES", debit="590"),
    ]
    books = [
        book("payment:1", d(3), "25000", True, "412345678901"),
        book("payment:2", d(3), "50000", True),
        book("payment:3", d(4), "12400", True, "412345678902"),
        book("cash:1", d(5), "150000", True),
        book("payment:4", d(6), "25000", True, "412345678903"),
        book("payment:5", d(7), "300000", False),
        book("payment:6", d(8), "9900", True, "412345678904"),
        book("payment:7", d(10), "7500", True, "412345678905"),
        book("payment:8", d(9), "8000", True, "999999999999"),  # never reached the bank
    ]
    return lines, books


def test_eight_of_ten_lines_match_and_two_are_listed_unmatched() -> None:
    lines, books = october()
    result = c.match_statement(lines, books, window_days=3)
    assert len(result.matched) == 8
    assert sorted(result.unmatched_lines) == [8, 10]
    assert result.unmatched_books == ["payment:8"]


def test_a_reference_beats_an_earlier_line_with_the_same_amount() -> None:
    # Two ₹25,000 credits and two ₹25,000 receipts: each pairs with its own reference even
    # though the first receipt is the nearer one in date to the second line.
    d = lambda n: date(2026, 10, n)  # noqa: E731
    lines = [
        line(1, d(3), "UPI/B/555566667777", "25000"),
        line(2, d(4), "UPI/A/111122223333", "25000"),
    ]
    books = [
        book("p:A", d(3), "25000", True, "111122223333"),
        book("p:B", d(4), "25000", True, "555566667777"),
    ]
    result = c.match_statement(lines, books, window_days=3)
    pairs = {m.line_id: (m.key, m.how) for m in result.matched}
    assert pairs == {1: ("p:B", "reference"), 2: ("p:A", "reference")}


def test_amount_and_date_matches_the_nearest_day_and_each_book_entry_is_used_once() -> None:
    d = lambda n: date(2026, 10, n)  # noqa: E731
    lines = [line(1, d(5), "NEFT X", "1000"), line(2, d(6), "NEFT Y", "1000")]
    books = [book("p:1", d(5), "1000", True)]
    result = c.match_statement(lines, books, window_days=3)
    assert [(m.line_id, m.key, m.how) for m in result.matched] == [(1, "p:1", "amount")]
    assert result.unmatched_lines == [2]


def test_outside_the_window_or_wrong_direction_does_not_match() -> None:
    d = lambda n: date(2026, 10, n)  # noqa: E731
    lines = [line(1, d(1), "IN", "500"), line(2, d(20), "OUT", debit="700")]
    books = [book("p:1", d(10), "500", True), book("p:2", d(20), "700", True)]
    result = c.match_statement(lines, books, window_days=3)
    assert result.matched == []
    assert sorted(result.unmatched_lines) == [1, 2]
    assert sorted(result.unmatched_books) == ["p:1", "p:2"]


def test_short_references_are_not_trusted() -> None:
    d = lambda n: date(2026, 10, n)  # noqa: E731
    lines = [line(1, d(5), "UPI 12 ABC", "1000"), line(2, d(5), "UPI 7777 8888", "1000")]
    books = [book("p:1", d(5), "1000", True, "12"), book("p:2", d(5), "1000", True, "7777-8888")]
    result = c.match_statement(lines, books, window_days=3)
    assert {m.line_id: m.how for m in result.matched} == {1: "amount", 2: "reference"}


def test_round_numbers() -> None:
    assert c.is_round(D("10000"), D("1000"))
    assert c.is_round(D("1000.00"), D("1000"))
    assert not c.is_round(D("10500"), D("1000"))
    assert not c.is_round(D("760"), D("1000"))  # smaller than the step
    assert not c.is_round(D("5000"), D("0"))  # a zero step switches the rule off


def test_four_returns_in_thirty_days() -> None:
    hit = c.repeated_within(
        [date(2026, 10, 28), date(2026, 10, 2), date(2026, 10, 15), date(2026, 10, 9)], 4, 30
    )
    assert hit == (date(2026, 10, 2), date(2026, 10, 28), 4)
    miss = c.repeated_within(
        [date(2026, 10, 1), date(2026, 10, 10), date(2026, 10, 25), date(2026, 11, 3)], 4, 30
    )
    assert miss is None
    assert c.repeated_within([date(2026, 10, 1)] * 5, 4, 30) == (
        date(2026, 10, 1),
        date(2026, 10, 1),
        5,
    )
    assert c.repeated_within([], 4, 30) is None
    assert c.repeated_within([date(2026, 10, 1)] * 5, 0, 30) is None  # zero switches it off


def test_adjustment_the_day_before_a_count() -> None:
    assert c.days_before(date(2026, 10, 9), date(2026, 10, 10), 2) == 1
    assert c.days_before(date(2026, 10, 10), date(2026, 10, 10), 2) == 0
    assert c.days_before(date(2026, 10, 7), date(2026, 10, 10), 2) is None  # three days: too early
    assert c.days_before(date(2026, 10, 11), date(2026, 10, 10), 2) is None  # after the count


def test_cash_near_the_limit() -> None:
    # Limit ₹2,00,000 and 80 %: ₹1,60,000 and over is near the limit.
    assert c.near_limit(D("160000"), D("200000"), D("80"))
    assert not c.near_limit(D("159999.99"), D("200000"), D("80"))
    assert not c.near_limit(D("100"), D("0"), D("80"))
    assert not c.near_limit(D("100"), D("200000"), D("0"))  # zero switches it off


def test_back_dated_days() -> None:
    assert c.backdated_days(date(2026, 10, 3), date(2026, 10, 9)) == 6
    assert c.backdated_days(date(2026, 10, 9), date(2026, 10, 9)) == 0
    assert c.backdated_days(date(2026, 10, 12), date(2026, 10, 9)) == 0  # dated ahead, not behind


def test_period_lock() -> None:
    through = date(2026, 9, 30)
    assert c.is_locked(date(2026, 9, 30), through)
    assert c.is_locked(date(2026, 9, 1), through)
    assert not c.is_locked(date(2026, 10, 1), through)
    assert not c.is_locked(date(2020, 1, 1), None)


@pytest.mark.parametrize(
    ("new", "old", "reopens"),
    [
        (date(2026, 8, 31), date(2026, 9, 30), True),
        (None, date(2026, 9, 30), True),
        (date(2026, 10, 31), date(2026, 9, 30), False),
        (date(2026, 9, 30), None, False),
        (None, None, False),
    ],
)
def test_reopening_is_moving_the_lock_earlier(
    new: date | None, old: date | None, reopens: bool
) -> None:
    assert c.reopens(new, old) is reopens
