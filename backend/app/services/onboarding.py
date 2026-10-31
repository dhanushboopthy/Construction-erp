"""What every new company starts with: shop settings, a shop and a godown, the purchase charge
types, the walk-in customer and the expense categories. Used by the seed script and when a
Duolink admin creates a company. Safe to run twice: existing rows are left alone. Works for the
company set on the session (`set_tenant`) and does not commit."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenancy import current_tenant_id
from app.domain.landed_cost import ChargeBasis
from app.models.enums import LocationKind, PartyType
from app.models.masters import Party
from app.models.purchasing import CostComponent
from app.models.setup import Location, ShopSettings
from app.services import cashbook

# One shop and the godown; more are added in Settings, and every screen adapts.
STARTER_LOCATIONS = [
    ("S1", "Shop 1", LocationKind.SHOP),
    ("G1", "Godown", LocationKind.GODOWN),
]

# Charge types offered on a purchase line; the amounts are only suggestions (owner interview).
COST_COMPONENTS = [
    ("Unloading", ChargeBasis.PER_TON, "250"),
    ("Loading", ChargeBasis.PER_TON, "0"),
    ("Weighbridge", ChargeBasis.FLAT, "150"),
    ("Transport rent", ChargeBasis.PER_TRIP, "0"),
    ("Commission", ChargeBasis.FLAT, "0"),
    ("Others", ChargeBasis.FLAT, "0"),
]

WALK_IN = "Walk-in customer"


def ensure_basics(
    db: Session,
    *,
    legal_name: str,
    state_code: str,
    gstin: str | None = None,
    locations: list[tuple[str, str, LocationKind]] = STARTER_LOCATIONS,
) -> tuple[list[str], dict[str, Location]]:
    """Return what was created (for the seed script's report) and the locations by code."""
    tenant_id = current_tenant_id(db)
    notes: list[str] = []

    if db.execute(select(ShopSettings).where(ShopSettings.tenant_id == tenant_id)).first() is None:
        db.add(ShopSettings(legal_name=legal_name, gstin=gstin, state_code=state_code, address=""))
        notes.append("created shop settings (edit them in Settings)")

    by_code: dict[str, Location] = {
        loc.code: loc for loc in db.scalars(select(Location).where(Location.tenant_id == tenant_id))
    }
    for code, name, kind in locations:
        if code not in by_code:
            by_code[code] = Location(code=code, name=name, kind=kind, state_code=state_code)
            db.add(by_code[code])
            notes.append(f"created location {code} ({name})")
    db.flush()

    have = set(db.scalars(select(CostComponent.name).where(CostComponent.tenant_id == tenant_id)))
    for name, basis, amount in COST_COMPONENTS:
        if name not in have:
            db.add(CostComponent(name=name, basis=basis, default_amount=Decimal(amount)))
            notes.append(f"created charge type {name}")

    # Walk-in sales are normal B2C tax invoices to this party.
    if not db.execute(
        select(Party.id).where(Party.tenant_id == tenant_id, Party.name == WALK_IN)
    ).first():
        db.add(Party(name=WALK_IN, type=PartyType.CUSTOMER, state_code=state_code, address=""))
        notes.append(f"created party {WALK_IN}")

    cashbook.ensure_default_categories(db)
    return notes, by_code
