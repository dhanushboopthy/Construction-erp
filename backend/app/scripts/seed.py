"""Seed a company with shop settings, two shops, a godown and starter users.

    python -m app.scripts.seed                  # the default company (DEFAULT_TENANT_SLUG)
    python -m app.scripts.seed --tenant acme    # another company; created if it is new

Safe to run twice: existing rows are left alone. In production every password must come from
the environment (SEED_OWNER_PASSWORD, ...); the development defaults are refused there.
"""

import os
import secrets
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import services as _services  # noqa: F401 - registers audit listeners
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.core.tenancy import set_tenant
from app.domain.tenancy import check_slug
from app.models.enums import LocationKind, Role, TenantPlan, TenantStatus
from app.models.setup import AppUser
from app.models.tenancy import Tenant
from app.services import onboarding

DEV_PASSWORDS = {
    "owner": "owner-pass-123",
    "counter1": "counter-pass-123",
    "counter2": "counter-pass-123",
    "accounts": "accounts-pass-123",
}

# The starter shop and godown come from services/onboarding.py. The second shop (and its counter
# user) is created with SEED_SHOPS=2, or added later in Settings.
SECOND_SHOP = ("S2", "Shop 2", LocationKind.SHOP)

USERS = [
    ("owner", "Shop Owner", Role.OWNER, []),
    ("counter1", "Counter, Shop 1", Role.COUNTER, ["S1"]),
    ("accounts", "Accountant", Role.ACCOUNTANT, []),
]
SECOND_SHOP_USER = ("counter2", "Counter, Shop 2", Role.COUNTER, ["S2"])


def _password(username: str) -> tuple[str, bool]:
    """Return (password, generated?)."""
    env_value = os.environ.get(f"SEED_{username.upper()}_PASSWORD")
    if env_value:
        return env_value, False
    if get_settings().is_production:
        return secrets.token_urlsafe(12), True
    return DEV_PASSWORDS[username], False


def _tenant(db: Session, slug: str | None, shop_name: str, notes: list[str]) -> Tenant:
    """The company to seed, created (active) if it does not exist yet."""
    slug = check_slug(slug or get_settings().default_tenant_slug or "main")
    tenant = db.execute(select(Tenant).where(Tenant.slug == slug)).scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(slug=slug, name=shop_name, status=TenantStatus.ACTIVE, plan=TenantPlan.PRO)
        db.add(tenant)
        db.flush()
        notes.append(f"created company {slug}")
    return tenant


def seed(
    db: Session, *, tenant_slug: str | None = None, second_shop: bool | None = None
) -> list[str]:
    notes: list[str] = []
    if second_shop is None:
        second_shop = os.environ.get("SEED_SHOPS", "1").strip() == "2"
    state_code = os.environ.get("SEED_STATE_CODE", "33")  # 33 = Tamil Nadu
    shop_name = os.environ.get("SEED_SHOP_NAME", "Demo Construction Materials")

    tenant_id = _tenant(db, tenant_slug, shop_name, notes).id
    set_tenant(db, tenant_id)

    created, by_code = onboarding.ensure_basics(
        db,
        legal_name=shop_name,
        state_code=state_code,
        locations=onboarding.STARTER_LOCATIONS + ([SECOND_SHOP] if second_shop else []),
    )
    notes += created

    for username, full_name, role, codes in USERS + ([SECOND_SHOP_USER] if second_shop else []):
        exists = db.execute(
            select(AppUser.id).where(AppUser.tenant_id == tenant_id, AppUser.username == username)
        ).first()
        if exists:
            continue
        password, generated = _password(username)
        db.add(
            AppUser(
                tenant_id=tenant_id,
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


def main(argv: list[str]) -> int:
    if argv and (len(argv) != 2 or argv[0] != "--tenant"):
        print("usage: python -m app.scripts.seed [--tenant <company code>]")
        return 2
    with SessionLocal() as db:
        notes = seed(db, tenant_slug=argv[1] if argv else None)
    print("\n".join(notes) if notes else "Nothing to do: already seeded.")
    if get_settings().is_production and any("password:" in n for n in notes):
        print("Generated passwords are shown once. Store them safely and change them on first use.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
