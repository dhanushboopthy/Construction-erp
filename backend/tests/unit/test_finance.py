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
