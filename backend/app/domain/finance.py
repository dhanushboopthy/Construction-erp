"""Finance formulas (FM1, docs/FINANCE_REVIEW.md): net sales, gross and net profit, break-even,
and what a cash-book entry does to the shop's drawer. Pure functions; worked examples are in
tests/unit/test_finance.py. Names follow docs/GLOSSARY.md and domain/kpi_catalogue.py."""

from dataclasses import dataclass
from decimal import Decimal
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


def net_profit(ebitda_value: Numberish, interest: Numberish) -> Decimal:
    return money(to_decimal(ebitda_value) - to_decimal(interest))


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
