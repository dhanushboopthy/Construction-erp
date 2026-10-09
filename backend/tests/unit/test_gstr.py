"""Milestone 13: GSTR-1 table rules, document series, and GSTR-2B matching, worked by hand."""

from datetime import date
from decimal import Decimal as D

import pytest

from app.domain import gstr


def test_b2cl_is_an_inter_state_bill_to_an_unregistered_buyer_above_one_lakh():
    assert gstr.is_b2cl(registered=False, inter_state=True, invoice_value=D("100000.01"))
    assert not gstr.is_b2cl(registered=False, inter_state=True, invoice_value=D("100000"))
    assert not gstr.is_b2cl(registered=False, inter_state=False, invoice_value=D("500000"))
    assert not gstr.is_b2cl(registered=True, inter_state=True, invoice_value=D("500000"))


@pytest.mark.parametrize(
    ("unit", "code"),
    [
        ("kg", "KGS"),
        ("KG", "KGS"),
        ("bag", "BAG"),
        ("piece", "PCS"),
        ("pcs", "PCS"),
        ("bundle", "BDL"),
        ("metre", "MTR"),
        ("ton", "TON"),
        ("coil", "OTH"),
        ("", "OTH"),
    ],
)
def test_units_map_to_gst_quantity_codes(unit, code):
    assert gstr.uqc(unit) == code


def test_periods():
    assert gstr.parse_period("2026-10") == (2026, 10)
    assert gstr.period_bounds(2026, 2) == (date(2026, 2, 1), date(2026, 2, 28))
    assert gstr.period_bounds(2028, 2)[1] == date(2028, 2, 29)
    assert gstr.period_bounds(2026, 12)[1] == date(2026, 12, 31)
    assert gstr.filing_period(2026, 10) == "102026"
    for bad in ("2026-13", "26-10", "2026/10", "", "2026-1"):
        with pytest.raises(ValueError, match="period"):
            gstr.parse_period(bad)


def test_document_series_ranges_and_gaps():
    numbers = ["S1/26-27/00001", "S1/26-27/00002", "S1/26-27/00004", "G1/26-27/00001"]
    rows = gstr.document_series(numbers)
    by = {r.series: r for r in rows}
    s1 = by["S1/26-27"]
    # Bills 1, 2 and 4 exist: from 1 to 4, three issued, number 3 is missing.
    assert (s1.first, s1.last, s1.count, s1.gaps) == ("S1/26-27/00001", "S1/26-27/00004", 3, [3])
    assert by["G1/26-27"].gaps == [] and by["G1/26-27"].count == 1
    assert gstr.document_series([]) == []
    with pytest.raises(ValueError, match="document number"):
        gstr.document_series(["BROKEN"])


def test_document_numbers_are_matched_loosely():
    assert gstr.normalize_doc_no(" inv/26-27/0042 ") == "INV26270042"
    assert gstr.normalize_doc_no("INV-26-27-0042") == "INV26270042"


def book(gstin="33AAPFU0939F1Z2", no="B-1", taxable="1000", igst="0", cgst="90", sgst="90"):
    return gstr.BillFigures(gstin, no, D(taxable), D(igst), D(cgst), D(sgst))


def test_reconcile_matches_flags_differences_and_finds_the_missing():
    books = [
        book(no="B-1"),
        book(no="B-2", taxable="2000", cgst="180", sgst="180"),
        book(no="B-3"),
        book(gstin="29ABCDE1234F1Z5", no="X-9", taxable="500", igst="90", cgst="0", sgst="0"),
    ]
    portal = [
        book(no="b 1"),  # same bill, written differently
        book(no="B-2", taxable="2000", cgst="170", sgst="170"),  # tax is 20 short on the portal
        book(no="B-4", taxable="300", cgst="27", sgst="27"),  # not in our books
        book(gstin="29ABCDE1234F1Z5", no="X-9", taxable="500.50", igst="90.50", cgst="0", sgst="0"),
    ]
    result = gstr.reconcile(books, portal, tolerance=D("1"))
    status = {(r.gstin[:2], gstr.normalize_doc_no(r.number)): r.status for r in result}
    assert status[("33", "B1")] == "matched"
    assert status[("33", "B2")] == "mismatch"
    assert status[("33", "B3")] == "missing_in_2b"
    assert status[("33", "B4")] == "missing_in_books"
    assert status[("29", "X9")] == "matched"  # 50 paise and 50 paise: inside the ₹1 tolerance
    mismatch = next(r for r in result if r.status == "mismatch")
    assert mismatch.difference_tax == D("-20.00")  # 2B says 340, books say 360


def test_a_duplicate_bill_in_the_books_is_not_matched_twice():
    result = gstr.reconcile([book(no="B-1"), book(no="B-1")], [book(no="B-1")], tolerance=D("1"))
    assert sorted(r.status for r in result) == ["matched", "missing_in_2b"]
