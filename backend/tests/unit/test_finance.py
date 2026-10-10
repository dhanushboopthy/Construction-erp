"""Finance formulas (FM1). Hand-worked numbers for one month at the shop.

October, one shop and the godown:
  bills (taxable, excl. GST)          ₹20,00,000
  credit notes (taxable)                 ₹50,000
  net sales                          ₹19,50,000
  COGS at weighted average           ₹18,60,000
  freight on sales                       ₹20,000
  gross profit = 19,50,000 - 18,60,000 - 20,000 = ₹70,000
  gross margin = 70,000 ÷ 19,50,000 = 3.59 %

Expenses booked in the cash book:
  rent ₹25,000 (fixed) · salaries ₹60,000 (fixed) · power ₹6,000 (fixed)
  loading labour ₹8,000 (variable) · interest on the CC limit ₹12,000 (interest)
  operating expenses excl. interest = 25,000 + 60,000 + 6,000 + 8,000 = ₹99,000
  EBITDA = 70,000 - 99,000 = -₹29,000 · net profit = -29,000 - 12,000 = -₹41,000

Break-even:
  contribution = 19,50,000 - 18,60,000 - 20,000 - 8,000 = ₹62,000 (3.18 % of sales)
  fixed costs = 25,000 + 60,000 + 6,000 + 12,000 = ₹1,03,000
  break-even sales = 1,03,000 ÷ (62,000 ÷ 19,50,000) = ₹32,39,516.13
"""

from datetime import date
from decimal import Decimal

import pytest

from app.domain import finance as f
from app.domain.finance import CashEntryKind as K
from app.domain.finance import ExpenseNature as N

D = Decimal


def test_net_sales_and_gross_profit_for_october() -> None:
    net = f.net_sales(D("2000000"), D("50000"))
    assert net == D("1950000.00")
    gp = f.gross_profit(net, D("1860000"), D("20000"))
    assert gp == D("70000.00")
    assert f.margin_pct(gp, net) == D("3.59")


def test_margin_is_none_without_sales() -> None:
    assert f.margin_pct(D("100"), D("0")) is None


def test_opex_split_ebitda_and_net_profit() -> None:
    lines = [
        f.ExpenseLine("Rent", N.FIXED, D("25000")),
        f.ExpenseLine("Salaries", N.FIXED, D("60000")),
        f.ExpenseLine("Power", N.FIXED, D("6000")),
        f.ExpenseLine("Loading labour", N.VARIABLE, D("8000")),
        f.ExpenseLine("Interest", N.INTEREST, D("12000")),
    ]
    split = f.split_expenses(lines)
    assert split.operating == D("99000.00")
    assert split.interest == D("12000.00")
    assert split.fixed == D("103000.00")  # interest is a fixed cost for break-even
    assert split.variable == D("8000.00")
    ebitda = f.ebitda(D("70000"), split.operating)
    assert ebitda == D("-29000.00")
    assert f.net_profit(ebitda, split.interest) == D("-41000.00")


def test_break_even_sales_for_october() -> None:
    contribution = f.contribution(D("1950000"), D("1860000"), D("20000"), D("8000"))
    assert contribution == D("62000.00")
    assert f.break_even_sales(D("103000"), contribution, D("1950000")) == D("3239516.13")


@pytest.mark.parametrize(
    ("contribution", "sales"),
    [(D("0"), D("1950000")), (D("-500"), D("1950000")), (D("62000"), D("0"))],
)
def test_break_even_needs_a_positive_contribution(contribution: Decimal, sales: Decimal) -> None:
    assert f.break_even_sales(D("103000"), contribution, sales) is None


def test_cash_effect_on_the_drawer() -> None:
    """Opening ₹20,000; cash receipts ₹1,80,000; loading labour ₹2,000 in cash; ₹1,50,000
    deposited to the bank. Expected drawer = 20,000 + 1,80,000 - 2,000 - 1,50,000 = ₹48,000."""
    entries = [
        (K.EXPENSE, True, D("2000")),
        (K.BANK_DEPOSIT, True, D("150000")),
    ]
    effect = sum((f.cash_effect(k, cash, amt) for k, cash, amt in entries), D("0"))
    assert effect == D("-152000.00")
    assert D("20000") + D("180000") + effect == D("48000.00")


def test_cash_effect_by_kind_and_mode() -> None:
    assert f.cash_effect(K.EXPENSE, False, D("5000")) == D("0.00")  # paid by UPI or bank
    assert f.cash_effect(K.BANK_WITHDRAWAL, True, D("10000")) == D("10000.00")
    assert f.cash_effect(K.OWNER_DRAWING, True, D("3000")) == D("-3000.00")
    assert f.cash_effect(K.OWNER_CAPITAL, True, D("50000")) == D("50000.00")
    assert f.cash_effect(K.OWNER_CAPITAL, False, D("50000")) == D("0.00")


def test_a_reversal_undoes_the_original() -> None:
    original = f.cash_effect(K.EXPENSE, True, D("2000"))
    reversal = f.cash_effect(K.EXPENSE, True, D("2000"), reversal=True)
    assert original + reversal == D("0.00")


def test_transfers_between_cash_and_bank_must_be_cash() -> None:
    """A deposit takes notes to the bank and a withdrawal brings them back: never by UPI."""
    assert f.needs_cash_mode(K.BANK_DEPOSIT)
    assert f.needs_cash_mode(K.BANK_WITHDRAWAL)
    assert not f.needs_cash_mode(K.EXPENSE)


def test_approval_limit() -> None:
    assert not f.needs_approval(D("5000"), D("5000"))  # at the limit is fine
    assert f.needs_approval(D("5000.01"), D("5000"))
    assert not f.needs_approval(D("999999"), None)  # no limit set


def test_expense_amount_must_be_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        f.cash_effect(K.EXPENSE, True, D("0"))


def test_kpi_catalogue_is_consistent() -> None:
    from app.domain import kpi_catalogue as cat

    codes = [k.code for k in cat.CATALOGUE]
    assert len(codes) == len(set(codes)), "codes are unique"
    assert all(k.formula and k.meaning and k.example for k in cat.CATALOGUE)
    staff = {k.code for k in cat.definitions(owner=False)}
    assert "gross_profit" not in staff and "net_sales" in staff
    assert cat.get("net_profit").name == "Net profit"
    with pytest.raises(KeyError):
        cat.get("nope")


def test_the_migration_seeds_the_same_heads_as_the_service() -> None:
    import importlib.util
    from pathlib import Path

    from app.services.cashbook import DEFAULT_CATEGORIES

    path = next(Path("alembic/versions").glob("*_0015_cash_book_and_expenses.py"))
    spec = importlib.util.spec_from_file_location("m0015", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert [(n, nature.value) for n, nature in DEFAULT_CATEGORIES] == module.DEFAULT_HEADS


# ---------------------------------------------------------------- FM3: rate overrides
#
# The owner cuts a TMT price by hand. List rate (what the system would have charged) is
# ₹62 a kg; the owner bills ₹60 a kg.
#   1,000 kg x (62 - 60)      = ₹2,000 given away
#   500 kg raised 56 -> 57    = 500 x (56 - 57) = -₹500 (the owner charged more than the list)
#   a cement bag, 100 bags 380 -> 372.50 = 100 x 7.50 = ₹750


def test_override_effect_is_list_less_billed_times_quantity() -> None:
    assert f.override_effect("62", "60", "1000") == Decimal("2000.00")
    assert f.override_effect("56", "57", "500") == Decimal("-500.00")
    assert f.override_effect("380", "372.50", "100") == Decimal("750.00")


def test_override_effect_rounds_to_paise_and_knows_when_it_cannot_be_worked_out() -> None:
    # 0.333333 x 3 kg = 0.999999 -> ₹1.00
    assert f.override_effect("0.333333", "0", "3") == Decimal("1.00")
    assert f.override_effect(None, "60", "1000") is None  # older bill: no list rate was kept
    assert f.override_effect("62", "62", "1000") == Decimal("0.00")


def test_override_summary_splits_cuts_from_raises_and_counts_unpriced_lines() -> None:
    # 2,000 and 750 given away; 500 charged extra; one line with no list rate.
    summary = f.summarise_overrides([Decimal("2000"), Decimal("-500"), None, Decimal("750")])
    assert summary.cut == Decimal("2750.00")
    assert summary.raised == Decimal("500.00")
    assert summary.net == Decimal("2250.00")  # 2,750 - 500
    assert summary.lines == 4 and summary.unpriced == 1


def test_override_summary_of_nothing_is_zero_not_missing() -> None:
    summary = f.summarise_overrides([])
    assert (summary.cut, summary.raised, summary.net, summary.lines) == (
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.00"),
        0,
    )


def test_discount_leakage_adds_discounts_to_rate_cuts() -> None:
    # Rate cuts ₹2,750 + bill discounts ₹500 = ₹3,250 given away this month.
    assert f.discount_leakage("2750", "500") == Decimal("3250.00")


def test_price_realisation_is_billed_over_list_value() -> None:
    # Billed ₹60,000 of goods listed at ₹62,000: 60,000 ÷ 62,000 = 96.77 %.
    assert f.price_realisation_pct("60000", "62000") == Decimal("96.77")
    assert f.price_realisation_pct("60000", "0") is None  # nothing to divide by


def test_the_override_kpis_are_in_the_catalogue_and_owner_only() -> None:
    from app.domain import kpi_catalogue as cat

    for code in ("discount_leakage", "price_realisation_pct"):
        assert cat.get(code).owner_only is True
        assert code not in {k.code for k in cat.definitions(owner=False)}


# ---------------------------------------------------------------- FM5: working capital
#
# A 30-day month at the shop (docs/FINANCE_REVIEW.md, FM5):
#   average stock at cost  ₹1.20 crore     COGS               ₹1.93 crore
#   average receivables    ₹45,00,000      credit sales       ₹60,00,000
#   average payables       ₹20,00,000      purchases          ₹1.95 crore
#   supplier advances      ₹40,00,000
#   DIO = 1,20,00,000 ÷ 1,93,00,000 x 30      = 18.65 -> 18.7 days
#   DSO = 45,00,000 ÷ 60,00,000 x 30          = 22.5 days
#   DPO = 20,00,000 ÷ 1,95,00,000 x 30        = 3.08 -> 3.1 days
#   advance days = 40,00,000 ÷ 1,95,00,000 x 30 = 6.15 -> 6.2 days
#   CCC = 18.7 + 22.5 + 6.2 - 3.1             = 44.3 days (from the rounded figures)

CR = Decimal("10000000")
LAKH = Decimal("100000")
INVENTORY, COGS = Decimal("1.2") * CR, Decimal("1.93") * CR
RECEIVABLES, CREDIT_SALES = 45 * LAKH, 60 * LAKH
PAYABLES, PURCHASES, ADVANCES = 20 * LAKH, Decimal("1.95") * CR, 40 * LAKH


def test_the_hand_worked_month_gives_the_five_working_capital_days() -> None:
    assert f.dio_days(INVENTORY, COGS, 30) == Decimal("18.7")
    assert f.dso_days(RECEIVABLES, CREDIT_SALES, 30) == Decimal("22.5")
    assert f.dpo_days(PAYABLES, PURCHASES, 30) == Decimal("3.1")
    assert f.advance_days(ADVANCES, PURCHASES, 30) == Decimal("6.2")
    assert f.ccc_days(Decimal("18.7"), Decimal("22.5"), Decimal("6.2"), Decimal("3.1")) == Decimal(
        "44.3"
    )


def test_a_day_count_is_none_when_there_is_nothing_to_divide_by() -> None:
    assert f.dio_days(INVENTORY, "0", 30) is None  # no goods sold
    assert f.dso_days(RECEIVABLES, "0", 30) is None  # no credit sales
    assert f.dpo_days(PAYABLES, "0", 30) is None
    assert f.advance_days(ADVANCES, "0", 30) is None
    assert f.dio_days(INVENTORY, COGS, 0) is None  # no days
    assert f.ccc_days(None, Decimal("22.5"), Decimal("6.2"), Decimal("3.1")) is None
    assert f.ccc_days(Decimal("18.7"), Decimal("22.5"), None, Decimal("3.1")) is None


def test_zero_balances_are_zero_days_not_missing() -> None:
    # No stock to speak of, but goods were sold: 0 days.
    assert f.dio_days("0", COGS, 30) == Decimal("0.0")


def test_average_of_the_start_and_end_of_the_period() -> None:
    # Stock ₹1.1 crore on 1 Sept, ₹1.3 crore on 30 Sept: average ₹1.2 crore.
    assert f.average(Decimal("1.1") * CR, Decimal("1.3") * CR) == INVENTORY


def test_inventory_turnover_is_cogs_over_average_stock() -> None:
    # 1.93 ÷ 1.2 = 1.61 times in the month.
    assert f.inventory_turnover(COGS, INVENTORY) == Decimal("1.61")
    assert f.inventory_turnover(COGS, "0") is None


def test_cash_tied_up_and_working_capital() -> None:
    # Stock 1.2 crore + receivables 45 lakh + advances 40 lakh = ₹2.05 crore tied up;
    # less payables 20 lakh = ₹1.85 crore of working capital (cash and bank are not counted).
    tied = f.cash_tied_up(INVENTORY, RECEIVABLES, ADVANCES)
    assert tied == Decimal("20500000.00")
    assert f.working_capital(tied, PAYABLES) == Decimal("18500000.00")


def test_collection_efficiency() -> None:
    # Opening ₹1,00,000 + credit sales ₹60,000 = ₹1,60,000 to collect; ₹90,000 came in: 56.25 %.
    assert f.collection_efficiency_pct("90000", "100000", "60000") == Decimal("56.25")
    assert f.collection_efficiency_pct("0", "0", "0") is None


def test_credit_utilisation() -> None:
    # ₹4,00,000 owed against a ₹5,00,000 limit: 80 %. No limit: nothing to measure.
    assert f.credit_utilisation_pct("400000", "500000") == Decimal("80.00")
    assert f.credit_utilisation_pct("400000", "0") is None


# Overdue by due date, on 20 October 2026 (bills due on the dates shown):
#   due 25 Oct, ₹20,000  -> not yet due ("current")
#   due 10 Oct, ₹10,000  -> 10 days late: 1-15
#   due  4 Oct, ₹15,000  -> 16 days late: 16-30
#   due 10 Sep, ₹30,000  -> 40 days late: 31-60
#   due  1 Jul, ₹40,000  -> 111 days late: 60+
# Provision at 0 / 1 / 2 / 10 / 50 %: 0 + 100 + 300 + 3,000 + 20,000 = ₹23,400.

TODAY = date(2026, 10, 20)
OPEN = [
    f.OverdueItem(date(2026, 10, 25), Decimal("20000")),
    f.OverdueItem(date(2026, 10, 10), Decimal("10000")),
    f.OverdueItem(date(2026, 10, 4), Decimal("15000")),
    f.OverdueItem(date(2026, 9, 10), Decimal("30000")),
    f.OverdueItem(date(2026, 7, 1), Decimal("40000")),
]


def test_overdue_buckets_count_days_past_the_due_date() -> None:
    b = f.OverdueBucket
    assert f.overdue_bucket(date(2026, 10, 20), TODAY) is b.CURRENT  # due today: not late yet
    assert f.overdue_bucket(date(2026, 10, 19), TODAY) is b.DAYS_1_15
    assert f.overdue_bucket(date(2026, 10, 5), TODAY) is b.DAYS_1_15  # exactly 15 days late
    assert f.overdue_bucket(date(2026, 10, 4), TODAY) is b.DAYS_16_30  # 16 days
    assert f.overdue_bucket(date(2026, 9, 20), TODAY) is b.DAYS_16_30  # exactly 30
    assert f.overdue_bucket(date(2026, 9, 19), TODAY) is b.DAYS_31_60  # 31
    assert f.overdue_bucket(date(2026, 8, 21), TODAY) is b.DAYS_31_60  # exactly 60
    assert f.overdue_bucket(date(2026, 8, 20), TODAY) is b.OVER_60  # 61


def test_overdue_aging_sums_each_bucket() -> None:
    aged = f.overdue_aging(OPEN, TODAY)
    assert [aged[b] for b in f.OverdueBucket] == [
        Decimal("20000.00"),
        Decimal("10000.00"),
        Decimal("15000.00"),
        Decimal("30000.00"),
        Decimal("40000.00"),
    ]
    assert f.overdue_total(aged) == Decimal("95000.00")  # everything past its due date
    empty = f.overdue_aging([], TODAY)
    assert all(v == Decimal("0.00") for v in empty.values())


def test_provision_applies_a_percentage_to_each_bucket() -> None:
    pct = {
        f.OverdueBucket.CURRENT: Decimal("0"),
        f.OverdueBucket.DAYS_1_15: Decimal("1"),
        f.OverdueBucket.DAYS_16_30: Decimal("2"),
        f.OverdueBucket.DAYS_31_60: Decimal("10"),
        f.OverdueBucket.OVER_60: Decimal("50"),
    }
    assert f.provision(f.overdue_aging(OPEN, TODAY), pct) == Decimal("23400.00")


def test_a_write_off_cannot_exceed_what_the_customer_owes() -> None:
    assert f.can_write_off("45000", "45000") is True  # the whole balance
    assert f.can_write_off("45000", "45000.01") is False
    assert f.can_write_off("45000", "0") is False
    assert f.can_write_off("-500", "100") is False  # the customer is in credit


def test_bad_debts_come_off_net_profit() -> None:
    # EBITDA -₹29,000, interest ₹12,000, bad debts ₹5,000: -29,000 - 12,000 - 5,000 = -₹46,000.
    assert f.net_profit("-29000", "12000", "5000") == Decimal("-46000.00")
    assert f.net_profit("-29000", "12000") == Decimal("-41000.00")  # unchanged without write-offs


def test_stock_written_down_to_nrv_also_comes_off_net_profit() -> None:
    # -29,000 - 12,000 - 5,000 bad debts - 25,000 stock written down (25,000 kg x ₹1) = -₹71,000.
    assert f.net_profit("-29000", "12000", "5000", "25000") == Decimal("-71000.00")


def test_the_working_capital_kpis_are_in_the_catalogue() -> None:
    from app.domain import kpi_catalogue as cat

    codes = {k.code for k in cat.CATALOGUE}
    wanted = {
        "dio_days",
        "dso_days",
        "dpo_days",
        "advance_days",
        "ccc_days",
        "inventory_turnover",
        "cash_tied_up",
        "working_capital",
        "collection_efficiency_pct",
        "credit_utilisation_pct",
        "overdue_receivables",
        "provision_doubtful",
        "bad_debts",
    }
    assert wanted <= codes
    staff = {k.code for k in cat.definitions(owner=False)}
    for code in ("dio_days", "dpo_days", "advance_days", "ccc_days", "cash_tied_up", "bad_debts"):
        assert code not in staff  # supplier terms, stock value and write-offs: owner only
    assert {"dso_days", "overdue_receivables", "credit_utilisation_pct"} <= staff
