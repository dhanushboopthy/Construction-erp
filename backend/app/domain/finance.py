"""Finance formulas (FM1, docs/FINANCE_REVIEW.md): net sales, gross and net profit, break-even,
and what a cash-book entry does to the shop's drawer. Pure functions; worked examples are in
tests/unit/test_finance.py. Names follow docs/GLOSSARY.md and domain/kpi_catalogue.py."""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from app.domain.money import ZERO, Numberish, money, to_decimal


class CashEntryKind(StrEnum):
    """What a cash-book voucher records."""

    EXPENSE = "expense"  # rent, salaries, loading labour, power, interest, ...
    BANK_DEPOSIT = "bank_deposit"  # notes taken from the drawer to the bank
    BANK_WITHDRAWAL = "bank_withdrawal"  # cash brought from the bank into the drawer
    OWNER_DRAWING = "owner_drawing"  # the owner takes money out of the business
    OWNER_CAPITAL = "owner_capital"  # the owner puts money in


class ExpenseNature(StrEnum):
    """How an expense behaves: fixed costs decide break-even, interest sits below EBITDA."""

    FIXED = "fixed"  # rent, salaries, power: paid whatever the sales
    VARIABLE = "variable"  # loading labour, packing: grow with the tons sold
    INTEREST = "interest"  # interest on the cash-credit limit and bank charges


# Effect of one rupee of each kind on the drawer when it moves in cash.
_DRAWER_SIGN: dict[CashEntryKind, int] = {
    CashEntryKind.EXPENSE: -1,
    CashEntryKind.BANK_DEPOSIT: -1,
    CashEntryKind.BANK_WITHDRAWAL: 1,
    CashEntryKind.OWNER_DRAWING: -1,
    CashEntryKind.OWNER_CAPITAL: 1,
}


def needs_cash_mode(kind: CashEntryKind) -> bool:
    """A deposit or a withdrawal moves notes between the drawer and the bank."""
    return kind in (CashEntryKind.BANK_DEPOSIT, CashEntryKind.BANK_WITHDRAWAL)


def cash_effect(
    kind: CashEntryKind, in_cash: bool, amount: Numberish, *, reversal: bool = False
) -> Decimal:
    """Rupees this voucher adds to (+) or takes from (-) the drawer. Money paid by UPI or bank
    does not touch the drawer. A reversal undoes the original exactly."""
    value = to_decimal(amount)
    if value <= ZERO:
        raise ValueError("the amount must be positive")
    if not in_cash and not needs_cash_mode(kind):
        return money(ZERO)
    sign = _DRAWER_SIGN[kind] * (-1 if reversal else 1)
    return money(value * sign)


def needs_approval(amount: Numberish, limit: Numberish | None) -> bool:
    """Above the shop's limit, a counter user needs the owner's PIN."""
    return limit is not None and to_decimal(amount) > to_decimal(limit)


def net_sales(sold_taxable: Numberish, returned_taxable: Numberish) -> Decimal:
    """Bills less credit notes, both excluding GST."""
    return money(to_decimal(sold_taxable) - to_decimal(returned_taxable))


def gross_profit(
    net: Numberish, cogs: Numberish, freight: Numberish, stock_loss: Numberish = ZERO
) -> Decimal:
    """Net sales less the cost of the goods sold, the freight paid to deliver them and the
    stock lost through adjustments (FM2: breakage, theft, shortages; gains reduce it)."""
    return money(to_decimal(net) - to_decimal(cogs) - to_decimal(freight) - to_decimal(stock_loss))


def margin_pct(part: Numberish, whole: Numberish) -> Decimal | None:
    """Part as a percentage of whole, to 2 places; None when there is nothing to divide by."""
    base = to_decimal(whole)
    if base == ZERO:
        return None
    return (to_decimal(part) / base * 100).quantize(Decimal("0.01"))


@dataclass(frozen=True)
class ExpenseLine:
    category: str
    nature: ExpenseNature
    amount: Decimal


@dataclass(frozen=True)
class ExpenseSplit:
    operating: Decimal  # everything except interest (sits above EBITDA)
    interest: Decimal
    fixed: Decimal  # fixed + interest: what the business pays whatever it sells
    variable: Decimal


def split_expenses(lines: list[ExpenseLine]) -> ExpenseSplit:
    total = dict.fromkeys(ExpenseNature, ZERO)
    for line in lines:
        total[line.nature] += line.amount
    return ExpenseSplit(
        operating=money(total[ExpenseNature.FIXED] + total[ExpenseNature.VARIABLE]),
        interest=money(total[ExpenseNature.INTEREST]),
        fixed=money(total[ExpenseNature.FIXED] + total[ExpenseNature.INTEREST]),
        variable=money(total[ExpenseNature.VARIABLE]),
    )


def ebitda(gross: Numberish, operating_expenses: Numberish) -> Decimal:
    """Gross profit less operating expenses (interest excluded; no depreciation is booked)."""
    return money(to_decimal(gross) - to_decimal(operating_expenses))


def net_profit(
    ebitda_value: Numberish,
    interest: Numberish,
    bad_debts: Numberish = ZERO,
    write_downs: Numberish = ZERO,
) -> Decimal:
    """EBITDA less interest, the bad debts written off (FM5) and the stock written down to its
    realisable value (FM6) in the period."""
    return money(
        to_decimal(ebitda_value)
        - to_decimal(interest)
        - to_decimal(bad_debts)
        - to_decimal(write_downs)
    )


def contribution(
    net: Numberish,
    cogs: Numberish,
    freight: Numberish,
    variable_expenses: Numberish,
    stock_loss: Numberish = ZERO,
) -> Decimal:
    """What each rupee of sales leaves to pay the fixed costs. Stock loss grows with the goods
    handled, so it counts as variable."""
    return money(
        to_decimal(net)
        - to_decimal(cogs)
        - to_decimal(freight)
        - to_decimal(variable_expenses)
        - to_decimal(stock_loss)
    )


def break_even_sales(
    fixed_costs: Numberish, contribution_value: Numberish, net: Numberish
) -> Decimal | None:
    """Sales at which contribution pays the fixed costs: fixed ÷ (contribution ÷ net sales).
    None when there are no sales or nothing is contributed (no break-even exists)."""
    sales, contrib = to_decimal(net), to_decimal(contribution_value)
    if sales <= ZERO or contrib <= ZERO:
        return None
    return money(to_decimal(fixed_costs) * sales / contrib)


def override_effect(
    list_rate: Numberish | None, billed_rate: Numberish, base_qty: Numberish
) -> Decimal | None:
    """Rupees given away (+) or charged extra (-) by a hand-set price: (list rate - billed rate)
    x quantity, both per base unit and excluding GST. None when the bill kept no list rate."""
    if list_rate is None:
        return None
    return money((to_decimal(list_rate) - to_decimal(billed_rate)) * to_decimal(base_qty))


@dataclass(frozen=True)
class OverrideSummary:
    cut: Decimal  # rupees given away on lines billed below the list rate
    raised: Decimal  # rupees charged above the list rate
    net: Decimal  # cut - raised
    lines: int  # overridden lines, whether or not their effect is known
    unpriced: int  # lines with no list rate to compare with


def summarise_overrides(effects: list[Decimal | None]) -> OverrideSummary:
    known = [e for e in effects if e is not None]
    cut = sum((e for e in known if e > ZERO), ZERO)
    raised = sum((-e for e in known if e < ZERO), ZERO)
    return OverrideSummary(
        cut=money(cut),
        raised=money(raised),
        net=money(cut - raised),
        lines=len(effects),
        unpriced=len(effects) - len(known),
    )


def discount_leakage(rate_cuts: Numberish, discounts: Numberish) -> Decimal:
    """Everything the owner gave away at the counter: hand-set price cuts plus bill discounts."""
    return money(to_decimal(rate_cuts) + to_decimal(discounts))


def price_realisation_pct(billed_value: Numberish, list_value: Numberish) -> Decimal | None:
    """Billed value as a percentage of what the same goods were listed at; 100 means no leakage."""
    return margin_pct(billed_value, list_value)


# ---------------------------------------------------------------------------- profitability cuts

_KG_PER_TON = Decimal(1000)


def tons(kilograms: Numberish) -> Decimal:
    """Kilograms as tons, to 3 places: 10,000 kg = 10.000 t."""
    return (to_decimal(kilograms) / _KG_PER_TON).quantize(Decimal("0.001"), ROUND_HALF_UP)


def profit_per_unit(profit: Numberish, quantity: Numberish) -> Decimal | None:
    """Profit for each ton (or bag, or piece) sold, to the paisa. None when nothing was sold,
    never 0: an empty cut has no profit per ton. A loss comes out negative."""
    qty = to_decimal(quantity)
    if qty <= ZERO:
        return None
    return money(to_decimal(profit) / qty)


def margin_per_base_unit(profit: Numberish, base_quantity: Numberish) -> Decimal | None:
    """Profit for each base unit (kg, bag), to 4 places, since a kilogram earns paise."""
    qty = to_decimal(base_quantity)
    if qty <= ZERO:
        return None
    return (to_decimal(profit) / qty).quantize(Decimal("0.0001"), ROUND_HALF_UP)


def contribution_per_ton(
    net_sales: Numberish,
    cogs: Numberish,
    freight: Numberish,
    variable_expenses: Numberish,
    stock_lost: Numberish,
    tons_sold: Numberish,
) -> Decimal | None:
    """(net sales - COGS - freight - variable expenses - stock lost) per ton sold."""
    return profit_per_unit(
        contribution(net_sales, cogs, freight, variable_expenses, stock_lost), tons_sold
    )


def share_pct(part: Numberish, whole: Numberish) -> Decimal | None:
    """Part as a percentage of whole, to 2 places; None when whole is zero."""
    base = to_decimal(whole)
    if base == ZERO:
        return None
    return (to_decimal(part) / base * 100).quantize(Decimal("0.01"), ROUND_HALF_UP)


# ---------------------------------------------------------------------------- working capital


def _days_ratio(balance: Numberish, flow: Numberish, days: int) -> Decimal | None:
    """balance ÷ flow x days, to 1 place; None when there is no flow or no days to measure."""
    base = to_decimal(flow)
    if base <= ZERO or days <= 0:
        return None
    return (to_decimal(balance) / base * days).quantize(Decimal("0.1"), ROUND_HALF_UP)


def dio_days(average_stock: Numberish, cogs: Numberish, days: int) -> Decimal | None:
    """Days inventory outstanding: how long stock sits before it is sold."""
    return _days_ratio(average_stock, cogs, days)


def dso_days(average_receivables: Numberish, credit_sales: Numberish, days: int) -> Decimal | None:
    """Days sales outstanding: how long customers take to pay."""
    return _days_ratio(average_receivables, credit_sales, days)


def dpo_days(average_payables: Numberish, purchases: Numberish, days: int) -> Decimal | None:
    """Days payables outstanding: how long we take to pay suppliers."""
    return _days_ratio(average_payables, purchases, days)


def advance_days(average_advances: Numberish, purchases: Numberish, days: int) -> Decimal | None:
    """Supplier advance days: how many days of purchases are paid before the goods arrive."""
    return _days_ratio(average_advances, purchases, days)


def ccc_days(
    dio: Decimal | None, dso: Decimal | None, advance: Decimal | None, dpo: Decimal | None
) -> Decimal | None:
    """Cash conversion cycle: DIO + DSO + advance days - DPO, from the days as shown. None when
    any part cannot be worked out, so a missing figure never looks like a good one."""
    if dio is None or dso is None or advance is None or dpo is None:
        return None
    return dio + dso + advance - dpo


def average(opening: Numberish, closing: Numberish) -> Decimal:
    """The average of a balance at the start and the end of a period."""
    return money((to_decimal(opening) + to_decimal(closing)) / 2)


def inventory_turnover(cogs: Numberish, average_stock: Numberish) -> Decimal | None:
    """Times the stock was sold through in the period: COGS ÷ average stock at cost."""
    stock = to_decimal(average_stock)
    if stock <= ZERO:
        return None
    return (to_decimal(cogs) / stock).quantize(Decimal("0.01"), ROUND_HALF_UP)


def cash_tied_up(stock: Numberish, receivables: Numberish, supplier_advances: Numberish) -> Decimal:
    """Money sitting in stock, in customers' hands and in suppliers' hands."""
    return money(to_decimal(stock) + to_decimal(receivables) + to_decimal(supplier_advances))


def working_capital(tied_up: Numberish, payables: Numberish) -> Decimal:
    """Cash tied up less what we owe suppliers. Cash and bank balances are not counted."""
    return money(to_decimal(tied_up) - to_decimal(payables))


def collection_efficiency_pct(
    collections: Numberish, opening_receivables: Numberish, credit_sales: Numberish
) -> Decimal | None:
    """Collections as a share of everything there was to collect: opening dues + credit sales."""
    return margin_pct(collections, to_decimal(opening_receivables) + to_decimal(credit_sales))


def credit_utilisation_pct(outstanding: Numberish, limit: Numberish) -> Decimal | None:
    """How much of a customer's credit limit is used; None when they have no limit."""
    if to_decimal(limit) <= ZERO:
        return None
    return margin_pct(outstanding, limit)


class OverdueBucket(StrEnum):
    """How late an unpaid bill is, counted from its due date, not its bill date."""

    CURRENT = "current"  # not yet due, or due today
    DAYS_1_15 = "1-15"
    DAYS_16_30 = "16-30"
    DAYS_31_60 = "31-60"
    OVER_60 = "60+"


@dataclass(frozen=True)
class OverdueItem:
    due_date: date
    remaining: Decimal


def overdue_bucket(due_date: date, today: date) -> OverdueBucket:
    late = (today - due_date).days
    if late <= 0:
        return OverdueBucket.CURRENT
    if late <= 15:
        return OverdueBucket.DAYS_1_15
    if late <= 30:
        return OverdueBucket.DAYS_16_30
    if late <= 60:
        return OverdueBucket.DAYS_31_60
    return OverdueBucket.OVER_60


def overdue_aging(items: list[OverdueItem], today: date) -> dict[OverdueBucket, Decimal]:
    totals = dict.fromkeys(OverdueBucket, ZERO)
    for item in items:
        totals[overdue_bucket(item.due_date, today)] += item.remaining
    return {bucket: money(total) for bucket, total in totals.items()}


def overdue_total(aged: dict[OverdueBucket, Decimal]) -> Decimal:
    """Everything past its due date: all buckets except 'current'."""
    return money(sum((v for b, v in aged.items() if b is not OverdueBucket.CURRENT), ZERO))


def provision(aged: dict[OverdueBucket, Decimal], pct: dict[OverdueBucket, Decimal]) -> Decimal:
    """Money to set aside for bills that may never be paid: each bucket x its percentage."""
    return money(sum((aged[b] * pct[b] / 100 for b in OverdueBucket), ZERO))


def can_write_off(balance: Numberish, amount: Numberish) -> bool:
    """A write-off must be positive and no more than the customer owes."""
    value = to_decimal(amount)
    return value > ZERO and value <= to_decimal(balance)
