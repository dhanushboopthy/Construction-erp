"""Companies, as Duolink sees them: list with usage, create with a first owner, change the plan,
suspend and reactivate. Counts only, never amounts (ADR 0012)."""

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, Select, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.security import hash_password
from app.core.tenancy import set_tenant
from app.domain.plans import limits_for, trial_end, trial_state
from app.domain.tenancy import check_slug
from app.models.auth import AuthSession
from app.models.enums import PlatformAction, Role, TenantPlan, TenantStatus
from app.models.sales import SalesInvoice
from app.models.setup import AppUser, Location
from app.models.tenancy import Tenant
from app.schemas.platform import TenantCreate, TenantDetail, TenantRow, TenantUpdate
from app.services import onboarding
from app.services.platform.audit import record


def _now() -> datetime:
    return datetime.now(UTC)


def _counts(db: Session, stmt: Select[int, int]) -> dict[int, int]:
    return {row[0]: row[1] for row in db.execute(stmt)}


def _usage(db: Session, tenant_ids: list[int]) -> dict[str, dict[int, int]]:
    since = (_now() - timedelta(days=30)).date()
    return {
        "users": _counts(
            db,
            select(AppUser.tenant_id, func.count())
            .where(AppUser.tenant_id.in_(tenant_ids), AppUser.is_active.is_(True))
            .group_by(AppUser.tenant_id),
        ),
        "locations": _counts(
            db,
            select(Location.tenant_id, func.count())
            .where(Location.tenant_id.in_(tenant_ids), Location.is_active.is_(True))
            .group_by(Location.tenant_id),
        ),
        "bills": _counts(
            db,
            select(SalesInvoice.tenant_id, func.count())
            .where(SalesInvoice.tenant_id.in_(tenant_ids), SalesInvoice.invoice_date >= since)
            .group_by(SalesInvoice.tenant_id),
        ),
    }


def _last_sign_ins(db: Session, tenant_ids: list[int]) -> dict[int, datetime | None]:
    rows = db.execute(
        select(AppUser.tenant_id, func.max(AppUser.last_login_at))
        .where(AppUser.tenant_id.in_(tenant_ids))
        .group_by(AppUser.tenant_id)
    )
    return {row[0]: row[1] for row in rows}


def _row(
    tenant: Tenant, usage: dict[str, dict[int, int]], last: dict[int, datetime | None]
) -> TenantRow:
    limits = limits_for(tenant.plan.value, tenant.max_users, tenant.max_locations)
    return TenantRow(
        id=tenant.id,
        slug=tenant.slug,
        name=tenant.name,
        status=tenant.status,
        plan=tenant.plan,
        trial_ends_at=tenant.trial_ends_at,
        trial_state=trial_state(tenant.trial_ends_at, _now()),
        users=usage["users"].get(tenant.id, 0),
        max_users=limits.max_users,
        locations=usage["locations"].get(tenant.id, 0),
        max_locations=limits.max_locations,
        bills_30d=usage["bills"].get(tenant.id, 0),
        last_sign_in_at=last.get(tenant.id),
        created_at=tenant.created_at,
    )


def list_tenants(
    db: Session,
    *,
    q: str | None = None,
    status: TenantStatus | None = None,
    plan: TenantPlan | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[TenantRow], int]:
    filters = []
    if q:
        like = f"%{q.strip()}%"
        filters.append(or_(Tenant.name.ilike(like), Tenant.slug.ilike(like)))
    if status:
        filters.append(Tenant.status == status)
    if plan:
        filters.append(Tenant.plan == plan)
    total = db.execute(select(func.count()).select_from(Tenant).where(*filters)).scalar_one()
    tenants = list(
        db.scalars(select(Tenant).where(*filters).order_by(Tenant.name).limit(limit).offset(offset))
    )
    ids = [t.id for t in tenants]
    usage, last = _usage(db, ids), _last_sign_ins(db, ids)
    return [_row(t, usage, last) for t in tenants], total


def get_tenant(db: Session, tenant_id: int) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFoundError("Company not found", code="TENANT_NOT_FOUND")
    return tenant


def detail(db: Session, tenant_id: int) -> TenantDetail:
    tenant = get_tenant(db, tenant_id)
    row = _row(tenant, _usage(db, [tenant.id]), _last_sign_ins(db, [tenant.id]))
    open_sessions = db.execute(
        select(func.count()).where(
            AuthSession.tenant_id == tenant.id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > _now(),
        )
    ).scalar_one()
    return TenantDetail(
        **row.model_dump(),
        own_max_users=tenant.max_users,
        own_max_locations=tenant.max_locations,
        suspended_at=tenant.suspended_at,
        suspended_reason=tenant.suspended_reason,
        open_sessions=open_sessions,
    )


def create_tenant(db: Session, data: TenantCreate, admin_id: int) -> Tenant:
    """The company, its shop settings and starter data, and its first owner: one transaction."""
    try:
        slug = check_slug(data.slug)
    except ValueError as exc:
        raise BusinessRuleError(str(exc), code="SLUG_INVALID", field="slug") from exc
    if db.execute(select(Tenant.id).where(Tenant.slug == slug)).first():
        raise ConflictError("That company code is taken", code="SLUG_TAKEN", field="slug")

    on_trial = data.plan is TenantPlan.TRIAL
    tenant = Tenant(
        slug=slug,
        name=data.name,
        plan=data.plan,
        status=TenantStatus.TRIAL if on_trial else TenantStatus.ACTIVE,
        trial_ends_at=trial_end(_now()) if on_trial else None,
    )
    db.add(tenant)
    try:
        db.flush()
    except IntegrityError as exc:  # two admins took the same code at once
        db.rollback()
        raise ConflictError("That company code is taken", code="SLUG_TAKEN", field="slug") from exc

    set_tenant(db, tenant.id)
    onboarding.ensure_basics(db, legal_name=data.name, state_code=data.state_code)
    db.add(
        AppUser(
            username=data.owner_username,
            full_name=data.owner_full_name,
            role=Role.OWNER,
            password_hash=hash_password(data.owner_password),
        )
    )
    record(
        db,
        PlatformAction.TENANT_CREATE,
        admin_id,
        tenant_id=tenant.id,
        details={"slug": slug, "plan": data.plan, "owner": data.owner_username},
    )
    db.commit()
    return tenant


def update_tenant(db: Session, tenant_id: int, data: TenantUpdate, admin_id: int) -> Tenant:
    tenant = get_tenant(db, tenant_id)
    changes: dict[str, dict[str, str | None]] = {}
    for key in sorted(data.model_fields_set):
        value = getattr(data, key)
        if key in {"name", "plan"} and value is None:
            continue  # these cannot be blank
        before = getattr(tenant, key)
        if before != value:
            changes[key] = {"from": _text(before), "to": _text(value)}
            setattr(tenant, key, value)
    paid = tenant.plan is not TenantPlan.TRIAL
    if "plan" in changes and paid and tenant.status is TenantStatus.TRIAL:
        tenant.status = TenantStatus.ACTIVE  # a paid plan ends the trial
    if changes:
        record(db, PlatformAction.TENANT_UPDATE, admin_id, tenant_id=tenant.id, details=changes)
    db.commit()
    return tenant


def _text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def suspend(db: Session, tenant_id: int, reason: str, admin_id: int) -> Tenant:
    """Nobody at the company can sign in or carry on; every open session ends now."""
    tenant = get_tenant(db, tenant_id)
    if tenant.status is TenantStatus.SUSPENDED:
        raise BusinessRuleError("This company is already suspended", code="ALREADY_SUSPENDED")
    tenant.status = TenantStatus.SUSPENDED
    tenant.suspended_at = _now()
    tenant.suspended_reason = reason
    ended = cast(
        "CursorResult[Any]",
        db.execute(
            update(AuthSession)
            .where(AuthSession.tenant_id == tenant.id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=_now())
        ),
    ).rowcount
    record(
        db,
        PlatformAction.TENANT_SUSPEND,
        admin_id,
        tenant_id=tenant.id,
        details={"reason": reason, "sessions_ended": ended},
    )
    db.commit()
    return tenant


def reactivate(db: Session, tenant_id: int, admin_id: int) -> Tenant:
    tenant = get_tenant(db, tenant_id)
    if tenant.status is not TenantStatus.SUSPENDED:
        raise BusinessRuleError("This company is not suspended", code="NOT_SUSPENDED")
    tenant.status = TenantStatus.TRIAL if tenant.plan is TenantPlan.TRIAL else TenantStatus.ACTIVE
    tenant.suspended_at = None
    tenant.suspended_reason = None
    record(db, PlatformAction.TENANT_REACTIVATE, admin_id, tenant_id=tenant.id)
    db.commit()
    return tenant
