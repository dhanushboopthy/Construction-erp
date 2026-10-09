"""Selling rates and price resolution (Milestone 5, rules B3 and B5, gap fixes G2 and G8)."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.tenancy import TENANT_ID
from app.domain import pricing
from app.domain.money import ZERO
from app.models.enums import PartyType
from app.models.masters import Item, Party
from app.models.rates import CustomerRate, ItemMargin, MarketRate
from app.schemas.rates import (
    CustomerRateCreate,
    CustomerRateOut,
    CustomerRateUpdate,
    HistoryPoint,
    MarginOut,
    MarginPut,
    MarketRatesPut,
    MarketRatesResult,
    RateRowOut,
    RateRowOwnerOut,
    RateWarning,
    ResolvedPriceOut,
)
from app.services import items as item_service
from app.services import ledgers
from app.services.shop_settings import get_settings_row

QUOTED_PLACES = Decimal("0.0001")


def _item(db: Session, item_id: int, field: str = "item_id") -> Item:
    item = db.get(Item, item_id)
    if item is None or item.tenant_id != TENANT_ID:
        raise NotFoundError("Item not found", field=field)
    return item


def _factor(item: Item, unit: str | None, field: str = "unit") -> tuple[str, Decimal]:
    """(unit name, factor to base) for a unit the item can be quoted in."""
    name = (unit or item.base_unit).lower()
    conversion = item_service.conversions(item).get(name)
    if conversion is None:
        raise BusinessRuleError(
            f"{item.name} has no unit called {unit!r}", code="UNKNOWN_UNIT", field=field
        )
    return name, conversion.factor_to_base


def _to_base_rate(
    item: Item, entered: Decimal, unit: str | None, includes_gst: bool
) -> tuple[str, Decimal]:
    """Rate per base unit excluding GST, from a rate quoted in some unit (G2)."""
    name, factor = _factor(item, unit)
    exclusive = pricing.exclusive_rate(entered, item.gst_rate, includes_gst=includes_gst)
    return name, pricing.rate_per_base_unit(exclusive, factor)


# ---------------------------------------------------------------------------- market rates


def latest_rates(db: Session, on: date) -> dict[int, list[MarketRate]]:
    """Per item: rates on or before `on`, newest first."""
    rows = db.execute(
        select(MarketRate)
        .where(MarketRate.tenant_id == TENANT_ID, MarketRate.effective_date <= on)
        .order_by(MarketRate.item_id, MarketRate.effective_date.desc())
    ).scalars()
    grouped: dict[int, list[MarketRate]] = {}
    for r in rows:
        grouped.setdefault(r.item_id, []).append(r)
    return grouped


def rate_board(db: Session, on: date, *, owner: bool) -> list[RateRowOut | RateRowOwnerOut]:
    items = list(
        db.execute(
            select(Item)
            .where(Item.tenant_id == TENANT_ID, Item.is_active.is_(True))
            .order_by(Item.name)
        ).scalars()
    )
    grouped = latest_rates(db, on)
    margins = {
        m.item_id: m.margin_per_base_unit
        for m in db.execute(select(ItemMargin).where(ItemMargin.tenant_id == TENANT_ID)).scalars()
    }
    out: list[RateRowOut | RateRowOwnerOut] = []
    for item in items:
        history = grouped.get(item.id, [])
        current = history[0] if history else None
        previous = history[1] if len(history) > 1 else None
        # Steel is quoted per ton; bags and pieces are quoted per bag or piece.
        quote_unit = (
            item.units[0].unit if item.units and not item.base_whole_only else item.base_unit
        )
        factor = item_service.conversions(item)[quote_unit].factor_to_base

        def quoted(value: Decimal | None, factor: Decimal = factor) -> Decimal | None:
            return None if value is None else (value * factor).quantize(QUOTED_PLACES)

        base = {
            "item_id": item.id,
            "item_name": item.name,
            "base_unit": item.base_unit,
            "rate": current.rate if current else None,
            "effective_date": current.effective_date if current else None,
            "previous_rate": previous.rate if previous else None,
            "units": sorted(item_service.conversions(item)),
            "quote_unit": quote_unit,
            "rate_quoted": quoted(current.rate if current else None),
            "previous_quoted": quoted(previous.rate if previous else None),
        }
        if not owner:
            out.append(RateRowOut(**base))
            continue
        position, _ = ledgers.stock_position(db, item.id)
        avg = position.avg_cost if position.quantity > ZERO else None
        margin = margins.get(item.id)
        suggested = (
            pricing.suggested_price(avg, margin) if avg is not None and margin is not None else None
        )
        check = (
            pricing.check_margin(current.rate, avg, item.min_margin)
            if current is not None and avg is not None
            else None
        )
        out.append(
            RateRowOwnerOut(
                **base,
                avg_cost=avg,
                margin_per_unit=margin,
                suggested_rate=suggested,
                margin_now=check.margin_per_unit if check else None,
                avg_cost_quoted=quoted(avg),
                margin_quoted=quoted(margin),
                suggested_quoted=quoted(suggested),
                margin_now_quoted=quoted(check.margin_per_unit if check else None),
                below_cost=check.below_cost if check else False,
                below_min_margin=check.below_min_margin if check else False,
            )
        )
    return out


def put_market_rates(db: Session, data: MarketRatesPut) -> MarketRatesResult:
    includes_gst = get_settings_row(db).rates_include_gst
    warnings: list[RateWarning] = []
    seen: set[int] = set()
    for entry in data.rates:
        if entry.item_id in seen:
            raise BusinessRuleError("An item appears twice", code="DUPLICATE_ITEM", field="rates")
        seen.add(entry.item_id)
        item = _item(db, entry.item_id)
        unit, base_rate = _to_base_rate(item, entry.rate, entry.unit, includes_gst)
        row = db.execute(
            select(MarketRate).where(
                MarketRate.tenant_id == TENANT_ID,
                MarketRate.item_id == item.id,
                MarketRate.effective_date == data.effective_date,
            )
        ).scalar_one_or_none()
        if row is None:
            db.add(
                MarketRate(
                    tenant_id=TENANT_ID,
                    item_id=item.id,
                    effective_date=data.effective_date,
                    rate=base_rate,
                    entered_unit=unit,
                    entered_rate=entry.rate,
                )
            )
        else:
            row.rate, row.entered_unit, row.entered_rate = base_rate, unit, entry.rate
        position, _ = ledgers.stock_position(db, item.id)
        if position.quantity > ZERO:
            check = pricing.check_margin(base_rate, position.avg_cost, item.min_margin)
            if check.below_cost or check.below_min_margin:
                warnings.append(
                    RateWarning(
                        item_id=item.id,
                        item_name=item.name,
                        below_cost=check.below_cost,
                        below_min_margin=check.below_min_margin,
                    )
                )
    db.commit()
    return MarketRatesResult(saved=len(data.rates), warnings=warnings)


def rate_history(db: Session, item_id: int, limit: int = 90) -> list[HistoryPoint]:
    _item(db, item_id)
    rows = db.execute(
        select(MarketRate)
        .where(MarketRate.tenant_id == TENANT_ID, MarketRate.item_id == item_id)
        .order_by(MarketRate.effective_date.desc())
        .limit(limit)
    ).scalars()
    return [
        HistoryPoint(
            effective_date=r.effective_date,
            rate=r.rate,
            entered_unit=r.entered_unit,
            entered_rate=r.entered_rate,
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------- customer rates


def _customer_view(db: Session, row: CustomerRate) -> CustomerRateOut:
    party = db.get(Party, row.party_id)
    item = db.get(Item, row.item_id)
    return CustomerRateOut(
        id=row.id,
        party_id=row.party_id,
        party_name=party.name if party else "",
        item_id=row.item_id,
        item_name=item.name if item else "",
        rate=row.rate,
        entered_unit=row.entered_unit,
        entered_rate=row.entered_rate,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        is_active=row.is_active,
    )


def create_customer_rate(db: Session, data: CustomerRateCreate) -> CustomerRateOut:
    party = db.get(Party, data.party_id)
    if party is None or party.tenant_id != TENANT_ID:
        raise NotFoundError("Customer not found", field="party_id")
    if party.type is PartyType.SUPPLIER:
        raise BusinessRuleError(
            "Rates are for customers", code="WRONG_PARTY_TYPE", field="party_id"
        )
    item = _item(db, data.item_id)
    overlap = db.execute(
        select(CustomerRate).where(
            CustomerRate.tenant_id == TENANT_ID,
            CustomerRate.party_id == party.id,
            CustomerRate.item_id == item.id,
            CustomerRate.is_active.is_(True),
        )
    ).scalars()
    for other in overlap:
        ends_before = other.valid_to is not None and other.valid_to < data.valid_from
        starts_after = data.valid_to is not None and other.valid_from > data.valid_to
        if not (ends_before or starts_after):
            raise ConflictError(
                f"This customer already has a rate for {item.name} from {other.valid_from}"
                + (f" to {other.valid_to}" if other.valid_to else " with no end date")
                + ". End it first.",
                code="RATE_PERIOD_OVERLAP",
                field="valid_from",
            )
    unit, base_rate = _to_base_rate(
        item, data.rate, data.unit, get_settings_row(db).rates_include_gst
    )
    row = CustomerRate(
        tenant_id=TENANT_ID,
        party_id=party.id,
        item_id=item.id,
        rate=base_rate,
        entered_unit=unit,
        entered_rate=data.rate,
        valid_from=data.valid_from,
        valid_to=data.valid_to,
    )
    db.add(row)
    db.commit()
    return _customer_view(db, row)


def update_customer_rate(db: Session, rate_id: int, data: CustomerRateUpdate) -> CustomerRateOut:
    row = db.get(CustomerRate, rate_id)
    if row is None or row.tenant_id != TENANT_ID:
        raise NotFoundError("Customer rate not found")
    changes = data.model_dump(exclude_unset=True)
    if "valid_to" in changes and changes["valid_to"] and changes["valid_to"] < row.valid_from:
        raise BusinessRuleError(
            "The end date cannot be before the start date", code="BAD_PERIOD", field="valid_to"
        )
    for key, value in changes.items():
        setattr(row, key, value)
    db.commit()
    return _customer_view(db, row)


def list_customer_rates(
    db: Session, party_id: int | None, item_id: int | None
) -> list[CustomerRateOut]:
    stmt = select(CustomerRate).where(CustomerRate.tenant_id == TENANT_ID)
    if party_id is not None:
        stmt = stmt.where(CustomerRate.party_id == party_id)
    if item_id is not None:
        stmt = stmt.where(CustomerRate.item_id == item_id)
    rows = db.execute(
        stmt.order_by(CustomerRate.party_id, CustomerRate.item_id, CustomerRate.valid_from.desc())
    )
    return [_customer_view(db, r) for r in rows.scalars()]


# ---------------------------------------------------------------------------- margins


def put_margins(db: Session, entries: list[MarginPut]) -> list[MarginOut]:
    for entry in entries:
        item = _item(db, entry.item_id)
        _, factor = _factor(item, entry.unit)
        per_unit = pricing.margin_per_base_unit(entry.margin, factor)
        row = db.execute(
            select(ItemMargin).where(
                ItemMargin.tenant_id == TENANT_ID, ItemMargin.item_id == item.id
            )
        ).scalar_one_or_none()
        if row is None:
            db.add(ItemMargin(tenant_id=TENANT_ID, item_id=item.id, margin_per_base_unit=per_unit))
        else:
            row.margin_per_base_unit = per_unit
    db.commit()
    return list_margins(db)


def list_margins(db: Session) -> list[MarginOut]:
    margins = {
        m.item_id: m.margin_per_base_unit
        for m in db.execute(select(ItemMargin).where(ItemMargin.tenant_id == TENANT_ID)).scalars()
    }
    items = db.execute(
        select(Item)
        .where(Item.tenant_id == TENANT_ID, Item.is_active.is_(True))
        .order_by(Item.name)
    ).scalars()
    return [
        MarginOut(
            item_id=i.id,
            item_name=i.name,
            base_unit=i.base_unit,
            margin_per_unit=margins.get(i.id, ZERO),
            min_margin=i.min_margin,
        )
        for i in items
    ]


# ---------------------------------------------------------------------------- resolution


def resolve(db: Session, item_id: int, party_id: int | None, on: date) -> ResolvedPriceOut:
    """Customer rate active on the date, else the latest market rate on or before it (B3)."""
    item = _item(db, item_id)
    customer_rates: list[pricing.CustomerRate] = []
    if party_id is not None:
        customer_rates = [
            pricing.CustomerRate(r.rate, r.valid_from, r.valid_to)
            for r in db.execute(
                select(CustomerRate).where(
                    CustomerRate.tenant_id == TENANT_ID,
                    CustomerRate.party_id == party_id,
                    CustomerRate.item_id == item_id,
                    CustomerRate.is_active.is_(True),
                )
            ).scalars()
        ]
    market = [
        pricing.MarketRate(r.rate, r.effective_date)
        for r in db.execute(
            select(MarketRate).where(
                MarketRate.tenant_id == TENANT_ID,
                MarketRate.item_id == item_id,
                MarketRate.effective_date <= on,
            )
        ).scalars()
    ]
    try:
        price = pricing.resolve_price(on, customer_rates, market)
    except pricing.PriceNotSetError as exc:
        raise BusinessRuleError(
            f"No rate is set for {item.name}. Ask the owner to enter today's rate.",
            code="PRICE_NOT_SET",
            field="item_id",
        ) from exc
    return ResolvedPriceOut(
        item_id=item.id,
        party_id=party_id,
        on=on,
        rate=price.rate,
        base_unit=item.base_unit,
        source=price.source,
    )
