"""Profit by brand, shop, user, item or customer for a calendar month (FM8, F19). Owner only.

Rows come from the same lines as the profit and loss (services/reports._lines): sold lines, and
negative rows for credit notes, with drop-ship cost from the link. Freight follows the lines of
the bill it was paid for. Stock lost (adjustments and counts) belongs to no brand or bill, so
the rows add up to gross profit *before* it, and the report shows the loss once at the foot: the
result equals the P&L gross profit for the same month and shop."""

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import today_ist
from app.core.errors import BusinessRuleError
from app.core.tenancy import TENANT_ID
from app.domain import finance
from app.domain.money import ZERO, money
from app.models.setup import AppUser, Location
from app.schemas.profitability import Cut, CutRow, ProfitabilityOut
from app.services import adjustments, reports
from app.services.finance import expenses_by_category, month_bounds

NO_BRAND = "No brand"
BY_WEIGHT = "kg"  # items whose base unit is the kilogram are counted in tons


@dataclass
class _Bucket:
    net_sales: Decimal = ZERO
    cogs: Decimal = ZERO
    freight: Decimal = ZERO
    kg: Decimal = ZERO
    weight_profit: Decimal = ZERO
    units: Decimal = ZERO
    unit_profit: Decimal = ZERO
    base_qty: Decimal = ZERO
    unit_names: set[str] = field(default_factory=set)


def _key(cut: Cut, x: reports._Line, places: dict[int, str], people: dict[int, str]) -> str:
    if cut is Cut.BRAND:
        return (x.brand or "").strip() or NO_BRAND
    if cut is Cut.SHOP:
        return places.get(x.location_id, "Unknown place")
    if cut is Cut.USER:
        return people.get(x.user_id, "Unknown") if x.user_id is not None else "Unknown"
    if cut is Cut.ITEM:
        return x.item
    return x.customer


def profitability(
    db: Session, period: str, cut: Cut, location_id: int | None = None
) -> ProfitabilityOut:
    date_from, date_to = month_bounds(period)
    if date_from > today_ist():
        raise BusinessRuleError("This month has not started yet", code="FUTURE_PERIOD")
    scope = frozenset({location_id}) if location_id is not None else None
    lines = reports._lines(db, date_from, date_to, scope)
    share = reports.freight_shares(db, lines)
    places = {p.id: f"{p.code} {p.name}" for p in db.scalars(select(Location))}
    people = {
        u.id: u.full_name for u in db.scalars(select(AppUser).where(AppUser.tenant_id == TENANT_ID))
    }

    buckets: dict[str, _Bucket] = defaultdict(_Bucket)
    for index, x in enumerate(lines):
        b = buckets[_key(cut, x, places, people)]
        profit = x.taxable - x.cost - share[index]
        b.net_sales += x.taxable
        b.cogs += x.cost
        b.freight += share[index]
        b.base_qty += x.base_qty
        b.unit_names.add(x.base_unit)
        if x.base_unit == BY_WEIGHT:
            b.kg += x.base_qty
            b.weight_profit += profit
        else:
            b.units += x.base_qty
            b.unit_profit += profit

    total_gross = money(
        sum((money(b.net_sales - b.cogs - b.freight) for b in buckets.values()), ZERO)
    )
    rows: list[CutRow] = []
    for key, b in buckets.items():
        gross = money(b.net_sales - b.cogs - b.freight)
        names = {n for n in b.unit_names if n != BY_WEIGHT}
        rows.append(
            CutRow(
                key=key,
                net_sales=money(b.net_sales),
                cogs=money(b.cogs),
                freight=money(b.freight),
                gross_profit=gross,
                margin_pct=finance.margin_pct(gross, b.net_sales),
                share_pct=finance.share_pct(gross, total_gross),
                tons=finance.tons(b.kg),
                units=b.units.quantize(Decimal("0.001")),
                unit_label=(names.pop() if len(names) == 1 else "units") if names else None,
                profit_per_ton=finance.profit_per_unit(b.weight_profit, finance.tons(b.kg)),
                profit_per_unit=finance.profit_per_unit(b.unit_profit, b.units),
                margin_per_base_unit=(
                    finance.margin_per_base_unit(gross, b.base_qty)
                    if len(b.unit_names) == 1
                    else None
                ),
            )
        )
    rows.sort(key=lambda r: (-r.gross_profit, r.key))

    net = money(sum((r.net_sales for r in rows), ZERO))
    cogs = money(sum((r.cogs for r in rows), ZERO))
    freight = money(sum((r.freight for r in rows), ZERO))
    lost = adjustments.stock_loss(db, date_from, date_to, location_id)
    split = finance.split_expenses(expenses_by_category(db, date_from, date_to, location_id))
    tons = finance.tons(sum((b.kg for b in buckets.values()), ZERO))
    weight_profit = sum((b.weight_profit for b in buckets.values()), ZERO)
    mixed = any(b.units != ZERO for b in buckets.values())

    note: str | None = None
    if not rows:
        note = "Not enough data yet: no bills in this month."
    elif mixed:
        note = (
            "Some sales were by the bag or piece, so one contribution per ton for the whole "
            "business would mislead. Profit per ton counts the lines sold by weight."
        )
    return ProfitabilityOut(
        period=period,
        by=cut,
        date_from=date_from,
        date_to=date_to,
        location_id=location_id,
        rows=rows,
        net_sales=net,
        cogs=cogs,
        freight=freight,
        gross_profit_before_loss=total_gross,
        stock_lost=lost,
        gross_profit=finance.gross_profit(net, cogs, freight, lost),
        tons=tons,
        profit_per_ton=finance.profit_per_unit(weight_profit, tons),
        variable_expenses=split.variable,
        contribution_per_ton=(
            None
            if mixed
            else finance.contribution_per_ton(net, cogs, freight, split.variable, lost, tons)
        ),
        enough_data=bool(rows),
        data_note=note,
    )
