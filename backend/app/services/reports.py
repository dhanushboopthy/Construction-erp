"""Owner and accountant reports (Milestone 12): the Today strip, profit by item, customer or
site, and sales by customer segment. Everything is worked out from issued documents."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import today_ist
from app.core.errors import BusinessRuleError
from app.core.tenancy import TENANT_ID
from app.domain import closing as closing_rules
from app.domain.fiscal import fy_label, fy_months, fy_start_year
from app.domain.money import ZERO, money, split_pro_rata
from app.models.enums import CustomerSegment, LedgerAccount
from app.models.masters import Item, Party, Site
from app.models.returns import CreditNote, CreditNoteLine
from app.models.sales import SalesInvoice, SalesLine
from app.models.transport import DropShipLink, Trip
from app.schemas.reports import (
    ProfitGroup,
    ProfitReport,
    ProfitRow,
    SegmentMonth,
    SegmentReport,
    TodayOut,
)
from app.services import ledgers
from app.services.shop_settings import get_settings_row

MAX_RANGE_DAYS = 366


@dataclass
class _Line:
    invoice_id: int
    item: str
    customer: str
    site: str
    taxable: Decimal
    cost: Decimal
    # FM8: what the profitability cuts group by. Quantity is in the item's base unit.
    item_id: int = 0
    brand: str | None = None
    base_unit: str = ""
    base_qty: Decimal = ZERO
    location_id: int = 0
    user_id: int | None = None


def _lines(
    db: Session, date_from: date, date_to: date, location_ids: frozenset[int] | None
) -> list[_Line]:
    """One row per sold line, and a negative row per returned line, with its cost."""
    scope = [SalesInvoice.tenant_id == TENANT_ID]
    if location_ids is not None:
        scope.append(SalesInvoice.location_id.in_(location_ids))
    links: dict[int, Decimal] = {
        r.sales_line_id: r.unit_cost
        for r in db.execute(select(DropShipLink.sales_line_id, DropShipLink.unit_cost))
    }
    out: list[_Line] = []
    sold = db.execute(
        select(SalesLine, SalesInvoice, Site.name, Item.brand, Item.base_unit)
        .join(SalesInvoice, SalesInvoice.id == SalesLine.invoice_id)
        .join(Item, Item.id == SalesLine.item_id)
        .outerjoin(Site, Site.id == SalesInvoice.site_id)
        .where(*scope, SalesInvoice.invoice_date >= date_from, SalesInvoice.invoice_date <= date_to)
    ).all()
    for line, inv, site_name, brand, base_unit in sold:
        unit = links.get(line.id, line.cost_per_unit)
        out.append(
            _Line(
                inv.id,
                line.description,
                inv.bill_to_name,
                site_name or "Collected from the shop",
                line.taxable,
                money(line.base_qty * unit),
                line.item_id,
                brand,
                base_unit,
                line.base_qty,
                inv.location_id,
                inv.created_by,
            )
        )
    returned = db.execute(
        select(CreditNoteLine, SalesLine, SalesInvoice, Site.name, Item.brand, Item.base_unit)
        .join(CreditNote, CreditNote.id == CreditNoteLine.credit_note_id)
        .join(SalesLine, SalesLine.id == CreditNoteLine.sales_line_id)
        .join(Item, Item.id == SalesLine.item_id)
        .join(SalesInvoice, SalesInvoice.id == CreditNote.invoice_id)
        .outerjoin(Site, Site.id == SalesInvoice.site_id)
        .where(*scope, CreditNote.note_date >= date_from, CreditNote.note_date <= date_to)
    ).all()
    for cn_line, line, inv, site_name, brand, base_unit in returned:
        unit = links.get(line.id, line.cost_per_unit)
        out.append(
            _Line(
                inv.id,
                line.description,
                inv.bill_to_name,
                site_name or "Collected from the shop",
                -cn_line.taxable,
                -money(cn_line.base_qty * unit),
                line.item_id,
                brand,
                base_unit,
                -cn_line.base_qty,
                inv.location_id,
                inv.created_by,
            )
        )
    return out


def _freight(db: Session, invoice_ids: set[int]) -> dict[int, Decimal]:
    if not invoice_ids:
        return {}
    rows = db.execute(
        select(Trip.invoice_id, func.sum(Trip.freight_amount))
        .where(Trip.tenant_id == TENANT_ID, Trip.invoice_id.in_(invoice_ids))
        .group_by(Trip.invoice_id)
    ).all()
    return {inv_id: money(total) for inv_id, total in rows if inv_id is not None}


def freight_shares(db: Session, lines: list[_Line]) -> dict[int, Decimal]:
    """An invoice's freight shared over its sold lines by taxable value, so it follows the item,
    customer, brand or site that earned it. Returned rows carry no freight of their own. The
    result is keyed by position in `lines`; the shares of an invoice add back to its freight."""
    freight = _freight(db, {x.invoice_id for x in lines})
    sold_by_invoice: dict[int, list[int]] = defaultdict(list)
    for index, x in enumerate(lines):
        if x.taxable > ZERO:
            sold_by_invoice[x.invoice_id].append(index)
    share: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for invoice_id, indices in sold_by_invoice.items():
        parts = split_pro_rata(freight.get(invoice_id, ZERO), [lines[i].taxable for i in indices])
        for i, part in zip(indices, parts, strict=True):
            share[i] = part
    return share


def profit_report(
    db: Session,
    group: ProfitGroup,
    date_from: date,
    date_to: date,
    location_ids: frozenset[int] | None = None,
) -> ProfitReport:
    if date_to < date_from:
        raise BusinessRuleError("The end date is before the start date", code="BAD_RANGE")
    if (date_to - date_from).days > MAX_RANGE_DAYS:
        raise BusinessRuleError("Choose a range of a year or less", code="RANGE_TOO_LONG")
    lines = _lines(db, date_from, date_to, location_ids)
    share = freight_shares(db, lines)
    totals: dict[str, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO, ZERO])
    for index, x in enumerate(lines):
        key = {
            ProfitGroup.ITEM: x.item,
            ProfitGroup.CUSTOMER: x.customer,
            ProfitGroup.SITE: f"{x.customer}: {x.site}",
        }[group]
        bucket = totals[key]
        bucket[0] += x.taxable
        bucket[1] += x.cost
        bucket[2] += share[index]
    rows = [
        ProfitRow(
            key=key,
            taxable=money(t),
            cost=money(c),
            freight=money(f),
            profit=money(t - c - f),
            margin_pct=(money(t - c - f) / money(t) * 100).quantize(Decimal("0.01"))
            if money(t) != ZERO
            else None,
        )
        for key, (t, c, f) in totals.items()
    ]
    rows.sort(key=lambda r: (-r.profit, r.key))
    return ProfitReport(
        group=group,
        date_from=date_from,
        date_to=date_to,
        rows=rows,
        taxable=money(sum((r.taxable for r in rows), ZERO)),
        cost=money(sum((r.cost for r in rows), ZERO)),
        freight=money(sum((r.freight for r in rows), ZERO)),
        profit=money(sum((r.profit for r in rows), ZERO)),
    )


def profit_for_day(db: Session, location_id: int, on: date) -> Decimal:
    return profit_report(db, ProfitGroup.ITEM, on, on, frozenset({location_id})).profit


def today(
    db: Session, *, location_ids: frozenset[int] | None, see_payable: bool, see_profit: bool
) -> TodayOut:
    on = today_ist()
    stock = ledgers.stock_summary(db, with_cost=False)
    if location_ids is not None:
        in_scope = sum(
            1
            for item in stock
            if any(
                loc.location_id in location_ids and loc.quantity > ZERO for loc in item.locations
            )
        )
    else:
        in_scope = sum(1 for item in stock if item.quantity > ZERO)
    scope = [SalesInvoice.tenant_id == TENANT_ID, SalesInvoice.invoice_date == on]
    notes = [CreditNote.tenant_id == TENANT_ID, CreditNote.note_date == on]
    if location_ids is not None:
        scope.append(SalesInvoice.location_id.in_(location_ids))
        notes.append(CreditNote.location_id.in_(location_ids))
    sales = db.execute(
        select(func.coalesce(func.sum(SalesInvoice.grand_total), 0)).where(*scope)
    ).scalar_one()
    returns = db.execute(
        select(func.coalesce(func.sum(CreditNote.grand_total), 0)).where(*notes)
    ).scalar_one()
    taxable_sold = db.execute(
        select(func.coalesce(func.sum(SalesInvoice.taxable_value), 0)).where(*scope)
    ).scalar_one()
    taxable_returned = db.execute(
        select(func.coalesce(func.sum(CreditNote.taxable_value), 0)).where(*notes)
    ).scalar_one()
    return TodayOut(
        as_of=on,
        items_in_stock=in_scope,
        customers_owe=ledgers.dues_report(db, LedgerAccount.RECEIVABLE, on).total,
        we_owe=ledgers.dues_report(db, LedgerAccount.PAYABLE, on).total if see_payable else None,
        sales_today=money(sales),
        returns_today=money(returns),
        net_sales_today=money(taxable_sold - taxable_returned),
        profit_today=profit_report(db, ProfitGroup.ITEM, on, on, location_ids).profit
        if see_profit
        else None,
    )


def sales_by_segment(db: Session, start_year: int | None) -> SegmentReport:
    settings = get_settings_row(db)
    month_start = settings.financial_year_start_month
    year = start_year if start_year is not None else fy_start_year(today_ist(), month_start)
    months = fy_months(year, month_start)
    first = date(months[0][0], months[0][1], 1)
    last_y, last_m = months[-1]
    end = date(last_y + (last_m == 12), last_m % 12 + 1, 1) - timedelta(days=1)
    buckets: dict[str, dict[str, Decimal]] = {
        f"{y:04d}-{m:02d}": defaultdict(lambda: ZERO) for y, m in months
    }
    rows = db.execute(
        select(SalesInvoice.invoice_date, SalesInvoice.taxable_value, Party.segment)
        .join(Party, Party.id == SalesInvoice.party_id)
        .where(
            SalesInvoice.tenant_id == TENANT_ID,
            SalesInvoice.invoice_date >= first,
            SalesInvoice.invoice_date <= end,
        )
    ).all()
    credits = db.execute(
        select(CreditNote.note_date, CreditNote.taxable_value, Party.segment)
        .join(Party, Party.id == CreditNote.party_id)
        .where(
            CreditNote.tenant_id == TENANT_ID,
            CreditNote.note_date >= first,
            CreditNote.note_date <= end,
        )
    ).all()
    for on, taxable, segment in rows:
        buckets[closing_rules.month_key(on)][segment.value if segment else "unassigned"] += taxable
    for on, taxable, segment in credits:
        buckets[closing_rules.month_key(on)][segment.value if segment else "unassigned"] -= taxable
    out = []
    for key, parts in buckets.items():
        r, c, b, u = (
            money(parts[CustomerSegment.RETAIL.value]),
            money(parts[CustomerSegment.CONTRACTOR.value]),
            money(parts[CustomerSegment.BULK.value]),
            money(parts["unassigned"]),
        )
        out.append(
            SegmentMonth(
                month=key, retail=r, contractor=c, bulk=b, unassigned=u, total=r + c + b + u
            )
        )
    return SegmentReport(
        financial_year=fy_label(first, month_start),
        start_year=year,
        months=out,
        total=money(sum((m.total for m in out), ZERO)),
    )
