"""Returns: a credit or debit note takes back a share of a line, with GST reversed to match."""

from decimal import Decimal as D

import pytest

from app.domain import gst, returns


class TestProportionalTaxable:
    def test_a_full_return_gives_back_exactly_the_line(self):
        # 2,500 kg sold for 1,40,000.00; all 2,500 kg back: 1,40,000.00, no rounding drift.
        assert returns.returned_taxable(D("140000.00"), D("2500"), D("2500")) == D("140000.00")

    def test_a_part_return_is_pro_rata(self):
        # 7 bags for 2,663.15; 2 bags back = 2,663.15 x 2 / 7 = 760.90.
        assert returns.returned_taxable(D("2663.15"), D("7"), D("2")) == D("760.90")
        # 500 of 2,500 kg: 1,40,000 / 5 = 28,000.00.
        assert returns.returned_taxable(D("140000.00"), D("2500"), D("500")) == D("28000.00")

    def test_rounds_half_up_to_paise(self):
        # 100.00 for 3 units, 1 back = 33.333... -> 33.33; 2 back = 66.666... -> 66.67.
        assert returns.returned_taxable(D("100.00"), D("3"), D("1")) == D("33.33")
        assert returns.returned_taxable(D("100.00"), D("3"), D("2")) == D("66.67")

    def test_a_discounted_line_returns_the_discounted_value(self):
        # The line's taxable already has the discount taken off, so the credit does too.
        assert returns.returned_taxable(D("55500.00"), D("1000"), D("250")) == D("13875.00")


class TestCheckReturnable:
    def test_within_what_is_left_to_return(self):
        # 10 sold, 4 already returned: up to 6 more.
        returns.check_returnable(D("10"), D("4"), D("6"))

    def test_more_than_is_left_is_refused(self):
        with pytest.raises(ValueError, match="only 6"):
            returns.check_returnable(D("10"), D("4"), D("6.001"))

    def test_zero_or_negative_is_refused(self):
        with pytest.raises(ValueError, match="positive"):
            returns.check_returnable(D("10"), D("0"), D("0"))


class TestNoteTotals:
    def test_credit_note_reverses_cgst_and_sgst_and_rounds(self):
        # 2 bags of cement back from 7 (taxable 760.90 at 28%): CGST 14% = 106.526 -> 106.53 each;
        # before rounding 760.90 + 213.06 = 973.96, rounded to 974.00 (round-off +0.04).
        line = gst.line_tax(
            returns.returned_taxable(D("2663.15"), D("7"), D("2")),
            D("28"),
            gst.SupplyKind.INTRA_STATE,
        )
        totals = gst.invoice_totals([line])
        assert (line.cgst, line.sgst) == (D("106.53"), D("106.53"))
        assert (totals.grand_total, totals.round_off) == (D("974.00"), D("0.04"))
