"""Profit and loss for a calendar month (FM1, docs/FINANCE_REVIEW.md F1). Owner only.

Sales, COGS and freight come from the same rows as the profit report (services/reports.py), so
the two never disagree; expenses come from the cash book. Nothing is stored: every figure is
worked out from the documents on each request."""

import calendar
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import today_ist
from app.core.errors import BusinessRuleError
from app.core.tenancy import TENANT_ID
from app.domain import finance
from app.domain.finance import CashEntryKind
from app.domain.money import ZERO, money
from app.models.cashbook import CashEntry, ExpenseCategory
from app.schemas.finance import PnlExpense, PnlOut
from app.services import reports


def month_bounds(period: str) -> tuple[date, date]:
    """'2026-10' → 1 Oct 2026 to 31 Oct 2026 (calendar months, IST dates)."""
    try:
        year_text, month_text = period.split("-")
        year, month = int(year_text), int(month_text)
        start = date(year, month, 1)
    except ValueError as exc:
        raise BusinessRuleError(
            "Give the month as YYYY-MM, e.g. 2026-10", code="BAD_PERIOD", field="period"
        ) from exc
    return start, date(year, month, calendar.monthrange(year, month)[1])


def expenses_by_category(
    db: Session, date_from: date, date_to: date, location_id: int | None
) -> list[finance.ExpenseLine]:
    stmt = (
        select(CashEntry, ExpenseCategory)
        .join(ExpenseCategory, ExpenseCategory.id == CashEntry.category_id)
        .where(
            CashEntry.tenant_id == TENANT_ID,
            CashEntry.kind == CashEntryKind.EXPENSE,
            CashEntry.entry_date >= date_from,
            CashEntry.entry_date <= date_to,
        )
    )
    if location_id is not None:
        stmt = stmt.where(CashEntry.location_id == location_id)
    totals: dict[tuple[str, finance.ExpenseNature], Decimal] = defaultdict(lambda: ZERO)
    for entry, category in db.execute(stmt).all():
        sign = -1 if entry.reverses_id is not None else 1
        totals[(category.name, category.nature)] += entry.amount * sign
    lines = [
        finance.ExpenseLine(name, nature, money(amount))
        for (name, nature), amount in totals.items()
        if money(amount) != ZERO
    ]
    return sorted(lines, key=lambda x: (-x.amount, x.category))


def profit_and_loss(db: Session, period: str, location_id: int | None = None) -> PnlOut:
    date_from, date_to = month_bounds(period)
    if date_from > today_ist():
        raise BusinessRuleError("This month has not started yet", code="FUTURE_PERIOD")
    scope = frozenset({location_id}) if location_id is not None else None
    lines = reports._lines(db, date_from, date_to, scope)
    sold = money(sum((x.taxable for x in lines if x.taxable > ZERO), ZERO))
    returned = money(-sum((x.taxable for x in lines if x.taxable < ZERO), ZERO))
    cogs = money(sum((x.cost for x in lines), ZERO))
    freight = money(sum(reports._freight(db, {x.invoice_id for x in lines}).values(), ZERO))

    net = finance.net_sales(sold, returned)
    gross = finance.gross_profit(net, cogs, freight)
    expense_lines = expenses_by_category(db, date_from, date_to, location_id)
    split = finance.split_expenses(expense_lines)
    ebitda = finance.ebitda(gross, split.operating)
    net_profit = finance.net_profit(ebitda, split.interest)
    contribution = finance.contribution(net, cogs, freight, split.variable)

    enough = bool(lines) or bool(expense_lines)
    note: str | None = None
    if not enough:
        note = "Not enough data yet: no bills or expenses in this month."
    elif not lines:
        note = "No sales in this month yet, so margins and break-even cannot be worked out."
    elif not expense_lines:
        note = "No expenses booked this month: net profit equals gross profit until they are."

    return PnlOut(
        period=period,
        date_from=date_from,
        date_to=date_to,
        location_id=location_id,
        sales=sold,
        returns=returned,
        net_sales=net,
        cogs=cogs,
        freight=freight,
        gross_profit=gross,
        gross_margin_pct=finance.margin_pct(gross, net),
        expenses=[
            PnlExpense(category=x.category, nature=x.nature, amount=x.amount) for x in expense_lines
        ],
        opex=split.operating,
        ebitda=ebitda,
        interest=split.interest,
        net_profit=net_profit,
        net_margin_pct=finance.margin_pct(net_profit, net),
        fixed_costs=split.fixed,
        variable_costs=split.variable,
        contribution=contribution,
        break_even_sales=finance.break_even_sales(split.fixed, contribution, net),
        enough_data=enough,
        data_note=note,
    )
