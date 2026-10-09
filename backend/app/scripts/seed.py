"""Seed a fresh database with shop settings, two shops, a godown and starter users.

    python -m app.scripts.seed

Safe to run twice: existing rows are left alone. In production every password must come from
the environment (SEED_OWNER_PASSWORD, ...); the development defaults are refused there.
"""

import os
import secrets
import sys
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import services as _services  # noqa: F401 - registers audit listeners
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.core.tenancy import TENANT_ID
from app.domain.landed_cost import ChargeBasis
from app.models.enums import LocationKind, Role
from app.models.purchasing import CostComponent
from app.models.setup import AppUser, Location, ShopSettings

DEV_PASSWORDS = {
    "owner": "owner-pass-123",
    "counter1": "counter-pass-123",
    "counter2": "counter-pass-123",
    "accounts": "accounts-pass-123",
}

LOCATIONS = [
    ("S1", "Shop 1", LocationKind.SHOP),
    ("S2", "Shop 2", LocationKind.SHOP),
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

USERS = [
    ("owner", "Shop Owner", Role.OWNER, []),
    ("counter1", "Counter, Shop 1", Role.COUNTER, ["S1"]),
    ("counter2", "Counter, Shop 2", Role.COUNTER, ["S2"]),
    ("accounts", "Accountant", Role.ACCOUNTANT, []),
]


def _password(username: str) -> tuple[str, bool]:
    """Return (password, generated?)."""
    env_value = os.environ.get(f"SEED_{username.upper()}_PASSWORD")
    if env_value:
        return env_value, False
    if get_settings().is_production:
        return secrets.token_urlsafe(12), True
    return DEV_PASSWORDS[username], False


def seed(db: Session) -> list[str]:
    notes: list[str] = []
    state_code = os.environ.get("SEED_STATE_CODE", "33")  # 33 = Tamil Nadu

    if db.execute(select(ShopSettings).where(ShopSettings.tenant_id == TENANT_ID)).first() is None:
        db.add(
            ShopSettings(
                tenant_id=TENANT_ID,
                legal_name=os.environ.get("SEED_SHOP_NAME", "Demo Construction Materials"),
                state_code=state_code,
                address="",
            )
        )
        notes.append("created shop settings (edit them in Settings)")

    by_code: dict[str, Location] = {
        loc.code: loc
        for loc in db.execute(select(Location).where(Location.tenant_id == TENANT_ID)).scalars()
    }
    for code, name, kind in LOCATIONS:
        if code not in by_code:
            by_code[code] = Location(
                tenant_id=TENANT_ID, code=code, name=name, kind=kind, state_code=state_code
            )
            db.add(by_code[code])
            notes.append(f"created location {code} ({name})")
    db.flush()

    have = set(
        db.execute(select(CostComponent.name).where(CostComponent.tenant_id == TENANT_ID)).scalars()
    )
    for name, basis, amount in COST_COMPONENTS:
        if name not in have:
            db.add(
                CostComponent(
                    tenant_id=TENANT_ID, name=name, basis=basis, default_amount=Decimal(amount)
                )
            )
            notes.append(f"created charge type {name}")

    for username, full_name, role, codes in USERS:
        exists = db.execute(
            select(AppUser.id).where(AppUser.tenant_id == TENANT_ID, AppUser.username == username)
        ).first()
        if exists:
            continue
        password, generated = _password(username)
        db.add(
            AppUser(
                tenant_id=TENANT_ID,
                username=username,
                full_name=full_name,
                role=role,
                password_hash=hash_password(password),
                locations=[by_code[c] for c in codes],
            )
        )
        shown = f" password: {password}" if generated else ""
        notes.append(f"created user {username} ({role.value}){shown}")

    db.commit()
    return notes


def main() -> int:
    with SessionLocal() as db:
        notes = seed(db)
    print("\n".join(notes) if notes else "Nothing to do: already seeded.")
    if get_settings().is_production and any("password:" in n for n in notes):
        print("Generated passwords are shown once. Store them safely and change them on first use.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
