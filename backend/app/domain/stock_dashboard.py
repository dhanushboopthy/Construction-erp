"""Stock dashboard figures (owner request R5): how many items are in stock, which have run out,
and the stock at each place and in each category, valued at the weighted-average cost (B2).
Pure functions; worked examples are in tests/unit/test_stock_dashboard.py."""

from dataclasses import dataclass, field
from decimal import Decimal

from app.domain.money import ZERO, money


@dataclass(frozen=True)
class ItemStock:
    item_id: int
    name: str
    category: str
    avg_cost: Decimal  # per base unit
    by_place: dict[str, Decimal] = field(default_factory=dict)  # location code -> quantity

    @property
    def quantity(self) -> Decimal:
        return sum(self.by_place.values(), ZERO)


@dataclass(frozen=True)
class Group:
    """A place or a category: items with stock there, and their value at cost."""

    code: str  # location code or item category
    items: int
    value: Decimal


@dataclass(frozen=True)
class Summary:
    items_in_stock: int
    out_of_stock: list[ItemStock]  # sorted by name
    stock_value: Decimal
    places: list[Group]  # sorted by code
    categories: list[Group]  # sorted by category


def summarise(items: list[ItemStock]) -> Summary:
    places: dict[str, list[Decimal]] = {}
    categories: dict[str, list[Decimal]] = {}
    in_stock = 0
    out: list[ItemStock] = []
    total = ZERO
    for item in items:
        if item.quantity <= ZERO:
            out.append(item)
            continue
        in_stock += 1
        item_value = ZERO
        for code, qty in item.by_place.items():
            if qty <= ZERO:
                continue
            value = money(qty * item.avg_cost)
            row = places.setdefault(code, [ZERO, ZERO])
            row[0] += 1
            row[1] += value
            item_value += value
        cat = categories.setdefault(item.category, [ZERO, ZERO])
        cat[0] += 1
        cat[1] += item_value
        total += item_value
    return Summary(
        items_in_stock=in_stock,
        out_of_stock=sorted(out, key=lambda x: (x.name, x.item_id)),
        stock_value=money(total),
        places=[Group(k, int(v[0]), money(v[1])) for k, v in sorted(places.items())],
        categories=[Group(k, int(v[0]), money(v[1])) for k, v in sorted(categories.items())],
    )
