"""Companies, as Duolink sees them: a searchable list with usage, onboarding in one transaction,
the plan and contact record, suspend, cancel and reactivate. Counts only, never amounts
(ADR 0012)."""

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, Select, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.security import hash_password
from app.core.tenancy import tenant_context
from app.domain.plans import (
    ENDING_SOON_DAYS,
    OnboardingError,
    TrialState,
    is_trial_plan,
    onboarding_terms,
    trial_state,
)
from app.domain.tenancy import StatusChangeError, check_slug, status_after
from app.models.auth import AuthSession
from app.models.documents import Attachment
from app.models.enums import LocationKind, PlatformAction, Role, TenantStatus
from app.models.platform import PlatformPlan
from app.models.purchasing import Purchase
from app.models.sales import SalesInvoice
from app.models.setup import AppUser, Location, ShopSettings
from app.models.tenancy import Tenant
from app.schemas.platform import (
    TenantCreate,
    TenantDetail,
    TenantRow,
    TenantUpdate,
    TenantUsage,
)
from app.services import onboarding, tenant_logo
from app.services.platform.audit import record
from app.services.platform.plans import plan_for_company
from app.services.tenants import limits_of


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
    limits = limits_of(tenant)
    return TenantRow(
        id=tenant.id,
        slug=tenant.slug,
        name=tenant.name,
        status=tenant.status,
        plan=tenant.plan.code,
        plan_id=tenant.plan_id,
        plan_name=tenant.plan.name,
        owner_name=tenant.owner_name,
        city=tenant.city,
        state_code=tenant.state_code,
        trial_ends_at=tenant.trial_ends_at,
        trial_state=trial_state(tenant.trial_ends_at, _now()),
        users=usage["users"].get(tenant.id, 0),
        max_users=limits.max_users,
        locations=usage["locations"].get(tenant.id, 0),
        max_locations=limits.max_locations,
        bills_30d=usage["bills"].get(tenant.id, 0),
        last_sign_in_at=last.get(tenant.id),
        last_activity_at=tenant.last_activity_at,
        created_at=tenant.created_at,
    )


SORTS = ("name", "created", "last_activity", "users")
EXPIRING_DAYS = 30  # "expiring" is a trial ending within this many days (subscriptions: M21)


def _active_users_of_tenant() -> ColumnElement[int]:
    return (
        select(func.count())
        .where(AppUser.tenant_id == Tenant.id, AppUser.is_active.is_(True))
        .correlate(Tenant)
        .scalar_subquery()
    )


def _trial_filter(state: TrialState, now: datetime) -> ColumnElement[bool]:
    ends = Tenant.trial_ends_at
    soon = now + timedelta(days=ENDING_SOON_DAYS)
    return {
        TrialState.NONE: ends.is_(None),
        TrialState.ENDED: ends <= now,
        TrialState.ENDING: (ends > now) & (ends <= soon),
        TrialState.RUNNING: ends > soon,
    }[state]


def list_tenants(
    db: Session,
    *,
    q: str | None = None,
    status: TenantStatus | None = None,
    plan: str | None = None,
    trial: TrialState | None = None,
    expiring: bool = False,
    sort: str = "name",
    descending: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[TenantRow], int]:
    """Companies, searched by name, code, owner or GSTIN; filtered by status, plan, trial state
    or "expiring within 30 days"; sorted and paged."""
    now = _now()
    filters: list[ColumnElement[bool]] = []
    if q and q.strip():
        like = f"%{q.strip()}%"
        by_gstin = select(ShopSettings.id).where(
            ShopSettings.tenant_id == Tenant.id, ShopSettings.gstin.ilike(like)
        )
        filters.append(
            or_(
                Tenant.name.ilike(like),
                Tenant.slug.ilike(like),
                Tenant.owner_name.ilike(like),
                Tenant.owner_email.ilike(like),
                by_gstin.exists(),
            )
        )
    if status:
        filters.append(Tenant.status == status)
    if plan:
        filters.append(
            Tenant.plan_id.in_(
                select(PlatformPlan.id).where(PlatformPlan.code == plan.strip().upper())
            )
        )
    if trial:
        filters.append(_trial_filter(trial, now))
    if expiring:
        filters.append(Tenant.trial_ends_at.between(now, now + timedelta(days=EXPIRING_DAYS)))

    column: Any = {
        "name": func.lower(Tenant.name),
        "created": Tenant.created_at,
        "last_activity": Tenant.last_activity_at,
        "users": _active_users_of_tenant(),
    }[sort]
    ordering = column.desc().nulls_last() if descending else column.asc().nulls_last()

    total = db.execute(select(func.count()).select_from(Tenant).where(*filters)).scalar_one()
    tenants = list(
        db.scalars(
            select(Tenant)
            .where(*filters)
            .order_by(ordering, Tenant.id.desc() if descending else Tenant.id)
            .limit(limit)
            .offset(offset)
        )
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
        cancelled_at=tenant.cancelled_at,
        cancelled_reason=tenant.cancelled_reason,
        owner_email=tenant.owner_email,
        owner_mobile=tenant.owner_mobile,
        notes=tenant.notes,
        open_sessions=open_sessions,
    )


def create_tenant(db: Session, data: TenantCreate, admin_id: int) -> Tenant:
    """The whole onboarding form in one transaction: the company and its contact record, the
    seller details, its first shop and a godown, the starter data and its first owner."""
    try:
        slug = check_slug(data.slug)
    except ValueError as exc:
        raise BusinessRuleError(str(exc), code="SLUG_INVALID", field="slug") from exc
    if db.execute(select(Tenant.id).where(Tenant.slug == slug)).first():
        raise ConflictError("That company code is taken", code="SLUG_TAKEN", field="slug")
    plan = plan_for_company(db, data.plan)
    try:
        status, trial_ends_at = onboarding_terms(
            plan.code,
            start_active=data.start_active,
            trial_days=data.trial_days,
            now=_now(),
        )
    except OnboardingError as exc:
        raise BusinessRuleError(str(exc), code=exc.code, field="trial_days") from exc
    godown_code = "G2" if data.shop_code == "G1" else "G1"

    tenant = Tenant(
        slug=slug,
        name=data.name,
        plan=plan,
        status=TenantStatus(status),
        trial_ends_at=trial_ends_at,
        owner_name=data.owner_full_name,
        owner_email=data.owner_email,
        owner_mobile=data.owner_mobile,
        city=data.city,
        state_code=data.state_code,
    )
    db.add(tenant)
    try:
        db.flush()
    except IntegrityError as exc:  # two admins took the same code at once
        db.rollback()
        raise ConflictError("That company code is taken", code="SLUG_TAKEN", field="slug") from exc

    with tenant_context(db, tenant.id):
        onboarding.ensure_basics(
            db,
            legal_name=data.legal_name or data.name,
            state_code=data.state_code,
            gstin=data.registration_no,
            locations=[
                (data.shop_code, data.shop_name, LocationKind.SHOP),
                (godown_code, "Godown", LocationKind.GODOWN),
            ],
        )
        db.add(
            AppUser(
                username=data.owner_username,
                full_name=data.owner_full_name,
                role=Role.OWNER,
                password_hash=hash_password(data.owner_password),
                must_change_password=data.require_owner_password_change,
            )
        )
        record(
            db,
            PlatformAction.TENANT_CREATE,
            admin_id,
            tenant_id=tenant.id,
            details={
                "slug": slug,
                "plan": plan.code,
                "status": status,
                "owner": data.owner_username,
                "shop": data.shop_code,
                "owner_must_change_password": data.require_owner_password_change,
            },
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
        if key == "plan":
            if value.strip().upper() != tenant.plan.code:  # staying on a plan needs it active
                new_plan = plan_for_company(db, value)
                changes["plan"] = {"from": tenant.plan.code, "to": new_plan.code}
                tenant.plan = new_plan
            continue
        if isinstance(value, str) and not value.strip():
            value = None  # a blank contact field is cleared
        before = getattr(tenant, key)
        if before != value:
            changes[key] = {"from": _text(before), "to": _text(value)}
            setattr(tenant, key, value)
    paid = not is_trial_plan(tenant.plan.code)
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


def _transition(tenant: Tenant, action: str) -> TenantStatus:
    try:
        return TenantStatus(
            status_after(tenant.status.value, action, on_trial_plan=is_trial_plan(tenant.plan.code))
        )
    except StatusChangeError as exc:
        raise BusinessRuleError(str(exc), code=exc.code) from exc


def _end_sessions(db: Session, tenant: Tenant) -> int:
    return cast(
        "CursorResult[Any]",
        db.execute(
            update(AuthSession)
            .where(AuthSession.tenant_id == tenant.id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=_now())
        ),
    ).rowcount


def suspend(db: Session, tenant_id: int, reason: str, admin_id: int) -> Tenant:
    """Nobody at the company can sign in or carry on; every open session ends now."""
    tenant = get_tenant(db, tenant_id)
    tenant.status = _transition(tenant, "suspend")
    tenant.suspended_at = _now()
    tenant.suspended_reason = reason
    ended = _end_sessions(db, tenant)
    record(
        db,
        PlatformAction.TENANT_SUSPEND,
        admin_id,
        tenant_id=tenant.id,
        details={"reason": reason, "sessions_ended": ended},
    )
    db.commit()
    return tenant


def cancel(db: Session, tenant_id: int, reason: str, admin_id: int) -> Tenant:
    """The company has left. Every session ends and nobody can sign in; its data is kept, and a
    Super Admin may reopen it with a reason."""
    tenant = get_tenant(db, tenant_id)
    previous = tenant.status
    tenant.status = _transition(tenant, "cancel")
    tenant.cancelled_at = _now()
    tenant.cancelled_reason = reason
    ended = _end_sessions(db, tenant)
    record(
        db,
        PlatformAction.TENANT_CANCEL,
        admin_id,
        tenant_id=tenant.id,
        details={"reason": reason, "was": previous.value, "sessions_ended": ended},
    )
    db.commit()
    return tenant


def reactivate(db: Session, tenant_id: int, admin_id: int, reason: str | None = None) -> Tenant:
    tenant = get_tenant(db, tenant_id)
    was = tenant.status
    new_status = _transition(tenant, "reactivate")
    if was is TenantStatus.CANCELLED and not (reason and reason.strip()):
        raise BusinessRuleError(
            "Say why this closed company is being reopened.", code="REASON_REQUIRED", field="reason"
        )
    tenant.status = new_status
    tenant.suspended_at = None
    tenant.suspended_reason = None
    tenant.cancelled_at = None
    tenant.cancelled_reason = None
    details: dict[str, Any] = {"was": was.value}
    if reason:
        details["reason"] = reason
    record(db, PlatformAction.TENANT_REACTIVATE, admin_id, tenant_id=tenant.id, details=details)
    db.commit()
    return tenant


def usage(db: Session, tenant_id: int) -> TenantUsage:
    """What the company uses, as counts (ADR 0012). Never an amount."""
    tenant = get_tenant(db, tenant_id)
    today = _now().date()

    def bills(days: int) -> int:
        return db.execute(
            select(func.count()).where(
                SalesInvoice.tenant_id == tenant.id,
                SalesInvoice.invoice_date >= today - timedelta(days=days),
            )
        ).scalar_one()

    purchases = db.execute(
        select(func.count()).where(
            Purchase.tenant_id == tenant.id,
            Purchase.bill_date >= today - timedelta(days=30),
        )
    ).scalar_one()
    files, size = db.execute(
        select(func.count(), func.coalesce(func.sum(Attachment.size_bytes), 0)).where(
            Attachment.tenant_id == tenant.id
        )
    ).one()
    counts = _usage(db, [tenant.id])
    return TenantUsage(
        users=counts["users"].get(tenant.id, 0),
        shops=counts["locations"].get(tenant.id, 0),
        bills_7d=bills(7),
        bills_30d=bills(30),
        bills_90d=bills(90),
        purchases_30d=purchases,
        attachments=files,
        attachment_bytes=int(size),
    )


def set_logo(db: Session, tenant_id: int, data: bytes, admin_id: int) -> None:
    """Replace the company's logo, with the same checks as the owner's own upload."""
    tenant = get_tenant(db, tenant_id)
    content_type = tenant_logo.check(data)  # refuse before anything is written
    with tenant_context(db, tenant.id):
        record(
            db,
            PlatformAction.TENANT_LOGO_SET,
            admin_id,
            tenant_id=tenant.id,
            details={"type": content_type, "bytes": len(data)},
        )
        tenant_logo.save(db, data)


def remove_logo(db: Session, tenant_id: int, admin_id: int) -> None:
    tenant = get_tenant(db, tenant_id)
    with tenant_context(db, tenant.id):
        record(db, PlatformAction.TENANT_LOGO_REMOVE, admin_id, tenant_id=tenant.id)
        tenant_logo.remove(db)
