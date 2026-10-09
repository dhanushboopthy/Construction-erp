"""Milestone 3: party ledger balances, FIFO open items and aging, and stock replay.

Every number below was worked out by hand (see the comments)."""

from datetime import date
from decimal import Decimal as D

import pytest

from app.domain import ledger, stock_valuation
from app.domain.ledger import Account, LedgerEntry


def e(day: str, debit: str = "0", credit: str = "0", ref: str = "") -> LedgerEntry:
    return LedgerEntry(date.fromisoformat(day), D(debit), D(credit), ref)


class TestBalance:
    def test_receivable_is_debits_less_credits(self):
        entries = [e("2026-08-01", debit="10000"), e("2026-09-10", credit="4000")]
        # The customer owes 10,000 - 4,000 = 6,000.
        assert ledger.balance(entries, Account.RECEIVABLE) == D("6000.00")

    def test_payable_is_credits_less_debits(self):
        entries = [e("2026-08-01", credit="50000"), e("2026-08-05", debit="20000")]
        # We owe the supplier 50,000 - 20,000 = 30,000.
        assert ledger.balance(entries, Account.PAYABLE) == D("30000.00")

    def test_advance_shows_as_negative_receivable(self):
        # The customer paid 1,500 against 1,000 of bills: we hold 500 of theirs.
        entries = [e("2026-08-01", debit="1000"), e("2026-08-02", credit="1500")]
        assert ledger.balance(entries, Account.RECEIVABLE) == D("-500.00")


class TestOpenItems:
    def test_payment_clears_oldest_bill_first(self):
        entries = [
            e("2026-08-01", debit="10000", ref="A"),
            e("2026-09-01", debit="5000", ref="B"),
            e("2026-09-10", credit="12000"),
        ]
        # 12,000 clears bill A (10,000) and 2,000 of bill B, leaving 3,000 of B.
        result = ledger.open_items(entries, Account.RECEIVABLE)
        assert [(i.ref, i.remaining) for i in result.items] == [("B", D("3000.00"))]
        assert result.advance == D("0.00")

    def test_excess_payment_becomes_an_advance(self):
        entries = [e("2026-08-01", debit="1000", ref="A"), e("2026-08-02", credit="1500")]
        result = ledger.open_items(entries, Account.RECEIVABLE)
        assert result.items == [] and result.advance == D("500.00")

    def test_an_advance_is_used_by_the_next_bill(self):
        entries = [e("2026-09-01", credit="2000"), e("2026-09-05", debit="5000", ref="B")]
        # The 2,000 advance covers part of B: 5,000 - 2,000 = 3,000 still open, dated 5 Sep.
        result = ledger.open_items(entries, Account.RECEIVABLE)
        assert [(i.ref, i.remaining, i.entry_date) for i in result.items] == [
            ("B", D("3000.00"), date(2026, 9, 5))
        ]
        assert result.advance == D("0.00")

    def test_supplier_bills_are_credits(self):
        entries = [
            e("2026-08-01", credit="40000", ref="P1"),
            e("2026-08-20", debit="40000"),
            e("2026-09-01", credit="15000", ref="P2"),
        ]
        result = ledger.open_items(entries, Account.PAYABLE)
        assert [(i.ref, i.remaining) for i in result.items] == [("P2", D("15000.00"))]

    def test_same_day_entries_keep_the_order_given(self):
        entries = [e("2026-09-01", debit="500", ref="A"), e("2026-09-01", credit="500")]
        assert ledger.open_items(entries, Account.RECEIVABLE).items == []


class TestAging:
    def test_buckets_by_days_since_the_bill(self):
        today = date(2026, 10, 9)
        entries = [
            e("2026-10-01", debit="1000", ref="new"),  # 8 days old: 0-30
            e("2026-09-01", debit="2000", ref="mid"),  # 38 days old: 31-60
            e("2026-07-01", debit="4000", ref="old"),  # 100 days old: over 60
        ]
        aged = ledger.aging(ledger.open_items(entries, Account.RECEIVABLE), today)
        assert (aged.up_to_30, aged.days_31_60, aged.over_60) == (
            D("1000.00"),
            D("2000.00"),
            D("4000.00"),
        )
        assert aged.total == D("7000.00")

    def test_boundaries_belong_to_the_lower_bucket(self):
        today = date(2026, 10, 9)
        entries = [
            e("2026-09-09", debit="100"),  # exactly 30 days
            e("2026-09-08", debit="200"),  # 31 days
            e("2026-08-10", debit="300"),  # exactly 60 days
            e("2026-08-09", debit="400"),  # 61 days
        ]
        aged = ledger.aging(ledger.open_items(entries, Account.RECEIVABLE), today)
        assert (aged.up_to_30, aged.days_31_60, aged.over_60) == (D("100"), D("500"), D("400"))

    def test_a_future_dated_bill_counts_as_current(self):
        entries = [e("2026-10-20", debit="900")]
        aged = ledger.aging(ledger.open_items(entries, Account.RECEIVABLE), date(2026, 10, 9))
        assert aged.up_to_30 == D("900")


class TestStockReplay:
    def test_replay_follows_the_ledger(self):
        from app.domain.stock_valuation import StockMove

        moves = [
            StockMove(date(2026, 10, 1), "S1", D("100"), D("0"), D("50")),  # in 100 @ 50
            StockMove(date(2026, 10, 1), "G1", D("100"), D("0"), D("60")),  # in 100 @ 60
            # Average so far: (100x50 + 100x60) / 200 = 55.
            StockMove(date(2026, 10, 2), "G1", D("0"), D("40"), D("55")),  # transfer out
            StockMove(date(2026, 10, 2), "S1", D("40"), D("0"), D("55")),  # transfer in
            # A transfer in at the average leaves it unchanged: 55.
            StockMove(date(2026, 10, 3), "S1", D("0"), D("50"), D("55")),  # sale of 50
            # Sale leaves the average at 55; 150 left.
            StockMove(date(2026, 10, 4), "G1", D("50"), D("0"), D("61")),  # in 50 @ 61
        ]
        result = stock_valuation.replay(moves)
        # New average: (150 x 55 + 50 x 61) / 200 = (8,250 + 3,050) / 200 = 56.5.
        assert result.total == stock_valuation.StockPosition(D("200.000"), D("56.5000"))
        # S1: 100 + 40 - 50 = 90.  G1: 100 - 40 + 50 = 110.
        assert result.by_location == {"S1": D("90.000"), "G1": D("110.000")}

    def test_empty_ledger(self):
        result = stock_valuation.replay([])
        assert result.total == stock_valuation.EMPTY and result.by_location == {}

    def test_stock_that_runs_out_resets_the_average(self):
        from app.domain.stock_valuation import StockMove

        moves = [
            StockMove(date(2026, 10, 1), "S1", D("10"), D("0"), D("50")),
            StockMove(date(2026, 10, 2), "S1", D("0"), D("10"), D("50")),
            StockMove(date(2026, 10, 3), "S1", D("5"), D("0"), D("70")),
        ]
        # Nothing left after the sale, so the new stock sets the cost: 70.
        assert stock_valuation.replay(moves).total.avg_cost == D("70.0000")

    def test_selling_more_than_held_is_refused(self):
        from app.domain.stock_valuation import StockMove

        moves = [StockMove(date(2026, 10, 1), "S1", D("0"), D("5"), D("50"))]
        with pytest.raises(stock_valuation.NegativeStockError):
            stock_valuation.replay(moves)
