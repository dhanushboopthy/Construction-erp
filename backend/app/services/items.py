"""Item master: items, unit conversions and conversion queries (Milestone 2)."""

from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.tenancy import TENANT_ID
from app.domain.units import UnitConversion, convert
from app.models.enums import ItemCategory
from app.models.masters import Item, ItemUnit
from app.schemas.items import ItemCreate, ItemUnitIn, ItemUpdate

PIECE = "piece"


def list_items(
    db: Session,
    *,
    q: str | None = None,
    category: ItemCategory | None = None,
    include_inactive: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Item], int]:
    filters = [Item.tenant_id == TENANT_ID]
    if not include_inactive:
        filters.append(Item.is_active.is_(True))
    if category:
        filters.append(Item.category == category)
    if q:
        like = f"%{q.strip()}%"
        filters.append(or_(Item.name.ilike(like), Item.brand.ilike(like), Item.size.ilike(like)))
    total = db.execute(select(func.count()).select_from(Item).where(*filters)).scalar_one()
    rows = db.execute(
        select(Item).where(*filters).order_by(Item.name).limit(limit).offset(offset)
    ).scalars()
    return list(rows), total


def get_item(db: Session, item_id: int) -> Item:
    item = db.get(Item, item_id)
    if item is None or item.tenant_id != TENANT_ID:
        raise NotFoundError("Item not found")
    return item


def _name_taken(db: Session, name: str, except_id: int | None = None) -> bool:
    stmt = select(Item.id).where(Item.tenant_id == TENANT_ID, func.lower(Item.name) == name.lower())
    if except_id is not None:
        stmt = stmt.where(Item.id != except_id)
    return db.execute(stmt).first() is not None


def _units(rows: list[ItemUnitIn]) -> list[ItemUnit]:
    return [
        ItemUnit(
            tenant_id=TENANT_ID,
            unit=u.unit,
            factor_to_base=u.factor_to_base,
            whole_only=u.whole_only,
        )
        for u in rows
    ]


def _sync_units(item: Item, rows: list[ItemUnitIn]) -> None:
    """Update units in place so the (item, unit) unique key never clashes mid-flush."""
    wanted = {r.unit: r for r in rows}
    for existing in list(item.units):
        row = wanted.pop(existing.unit, None)
        if row is None:
            item.units.remove(existing)
        else:
            existing.factor_to_base = row.factor_to_base
            existing.whole_only = row.whole_only
    item.units.extend(_units(list(wanted.values())))


def apply_create(db: Session, data: ItemCreate) -> Item:
    """Add an item without committing (the importer commits once for the whole file)."""
    if _name_taken(db, data.name):
        raise ConflictError("An item with this name exists", code="ITEM_NAME_TAKEN", field="name")
    item = Item(
        tenant_id=TENANT_ID,
        **data.model_dump(exclude={"units"}),
        units=_units(data.units),
    )
    db.add(item)
    db.flush()
    return item


def create_item(db: Session, data: ItemCreate) -> Item:
    item = apply_create(db, data)
    db.commit()
    return item


def apply_update(db: Session, item: Item, data: ItemUpdate) -> Item:
    changes = data.model_dump(exclude_unset=True)
    units = changes.pop("units", None)
    if "name" in changes and _name_taken(db, changes["name"], item.id):
        raise ConflictError("An item with this name exists", code="ITEM_NAME_TAKEN", field="name")
    for key, value in changes.items():
        setattr(item, key, value)
    if units is not None:
        if any(u["unit"] == item.base_unit for u in units):
            raise BusinessRuleError(
                "The base unit is implicit; do not list it again",
                code="BASE_UNIT_LISTED",
                field="units",
            )
        _sync_units(item, [ItemUnitIn(**u) for u in units])
    db.flush()
    return item


def update_item(db: Session, item_id: int, data: ItemUpdate) -> Item:
    item = apply_update(db, get_item(db, item_id), data)
    db.commit()
    return item


def conversions(item: Item) -> dict[str, UnitConversion]:
    """Every unit the item can be counted in, keyed by name.

    The base unit has factor 1. When the item has a theoretical weight per piece and is
    counted in kg, "piece" is added automatically (G7) unless the owner listed their own."""
    table = {item.base_unit: UnitConversion(item.base_unit, Decimal("1"), item.base_whole_only)}
    for u in item.units:
        table[u.unit] = UnitConversion(u.unit, u.factor_to_base, u.whole_only)
    if item.weight_per_piece_kg and item.base_unit == "kg" and PIECE not in table:
        table[PIECE] = UnitConversion(PIECE, item.weight_per_piece_kg, whole_only=True)
    return table


def convert_quantity(
    db: Session, item_id: int, quantity: Decimal, from_unit: str, to_unit: str
) -> Decimal:
    table = conversions(get_item(db, item_id))
    source, target = table.get(from_unit.lower()), table.get(to_unit.lower())
    if source is None or target is None:
        missing, field = (from_unit, "from_unit") if source is None else (to_unit, "to_unit")
        raise BusinessRuleError(
            f"This item has no unit called {missing!r}. Known units: {', '.join(sorted(table))}",
            code="UNKNOWN_UNIT",
            field=field,
        )
    try:
        return convert(quantity, source, target)
    except ValueError as exc:
        raise BusinessRuleError(str(exc), code="UNIT_NOT_WHOLE") from exc
