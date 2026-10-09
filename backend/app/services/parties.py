"""Customers, suppliers and customer sites (Milestone 2)."""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.tenancy import TENANT_ID
from app.models.enums import PartyType
from app.models.masters import Party, Site
from app.schemas.parties import PartyCreate, PartyUpdate, SiteCreate, SiteUpdate

CREDIT_FIELDS = ("credit_allowed", "credit_limit", "credit_days")


def list_parties(
    db: Session,
    *,
    q: str | None = None,
    kind: str | None = None,
    include_inactive: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Party], int]:
    filters = [Party.tenant_id == TENANT_ID]
    if not include_inactive:
        filters.append(Party.is_active.is_(True))
    if kind == "customer":
        filters.append(Party.type.in_([PartyType.CUSTOMER, PartyType.BOTH]))
    elif kind == "supplier":
        filters.append(Party.type.in_([PartyType.SUPPLIER, PartyType.BOTH]))
    if q:
        like = f"%{q.strip()}%"
        filters.append(
            or_(Party.name.ilike(like), Party.phone.ilike(like), Party.gstin.ilike(like))
        )
    total = db.execute(select(func.count()).select_from(Party).where(*filters)).scalar_one()
    rows = db.execute(
        select(Party).where(*filters).order_by(Party.name).limit(limit).offset(offset)
    ).scalars()
    return list(rows), total


def get_party(db: Session, party_id: int) -> Party:
    party = db.get(Party, party_id)
    if party is None or party.tenant_id != TENANT_ID:
        raise NotFoundError("Party not found")
    return party


def _name_taken(db: Session, name: str, except_id: int | None = None) -> bool:
    stmt = select(Party.id).where(
        Party.tenant_id == TENANT_ID, func.lower(Party.name) == name.lower()
    )
    if except_id is not None:
        stmt = stmt.where(Party.id != except_id)
    return db.execute(stmt).first() is not None


def _owner_only_credit(is_owner: bool, fields: dict[str, object]) -> None:
    """Credit terms are an owner decision (B8): counter staff may not set them."""
    touched = [k for k in CREDIT_FIELDS if k in fields and fields[k] not in (None, False)]
    if touched and not is_owner:
        raise PermissionDeniedError("Only the owner can allow credit or set a credit limit")


def _check_gstin_state(gstin: str | None, state_code: str) -> None:
    """Check before changing anything, so a refused update leaves no half-edited row."""
    if gstin and gstin[:2] != state_code:
        raise BusinessRuleError(
            "The first two digits of the GSTIN must match the state code",
            code="GSTIN_STATE_MISMATCH",
            field="gstin",
        )


def create_party(db: Session, data: PartyCreate, *, is_owner: bool) -> Party:
    _owner_only_credit(is_owner, data.model_dump())
    if _name_taken(db, data.name):
        raise ConflictError("A party with this name exists", code="PARTY_NAME_TAKEN", field="name")
    party = Party(
        tenant_id=TENANT_ID,
        **data.model_dump(exclude={"sites"}),
        sites=[Site(tenant_id=TENANT_ID, **s.model_dump()) for s in data.sites],
    )
    db.add(party)
    db.commit()
    return party


def update_party(db: Session, party_id: int, data: PartyUpdate, *, is_owner: bool) -> Party:
    party = get_party(db, party_id)
    changes = data.model_dump(exclude_unset=True)
    _owner_only_credit(is_owner, changes)
    if "name" in changes and _name_taken(db, changes["name"], party.id):
        raise ConflictError("A party with this name exists", code="PARTY_NAME_TAKEN", field="name")
    _check_gstin_state(
        changes.get("gstin", party.gstin), changes.get("state_code", party.state_code)
    )
    for key, value in changes.items():
        setattr(party, key, value)
    if party.type is PartyType.SUPPLIER:
        party.segment = None
        party.credit_allowed = False
    db.commit()
    return party


def get_site(db: Session, site_id: int) -> Site:
    site = db.get(Site, site_id)
    if site is None or site.tenant_id != TENANT_ID:
        raise NotFoundError("Site not found")
    return site


def add_site(db: Session, party_id: int, data: SiteCreate) -> Site:
    party = get_party(db, party_id)
    if party.type is PartyType.SUPPLIER:
        raise BusinessRuleError(
            "Suppliers do not have delivery sites", code="SUPPLIER_HAS_NO_SITES"
        )
    if any(s.name.lower() == data.name.lower() for s in party.sites):
        raise ConflictError(
            "This customer already has a site with this name", code="SITE_NAME_TAKEN", field="name"
        )
    site = Site(tenant_id=TENANT_ID, party_id=party.id, **data.model_dump())
    db.add(site)
    db.commit()
    return site


def update_site(db: Session, site_id: int, data: SiteUpdate) -> Site:
    site = get_site(db, site_id)
    changes = data.model_dump(exclude_unset=True)
    _check_gstin_state(changes.get("gstin", site.gstin), changes.get("state_code", site.state_code))
    for key, value in changes.items():
        setattr(site, key, value)
    db.commit()
    return site
