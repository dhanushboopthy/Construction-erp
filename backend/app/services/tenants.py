"""Finding the company a request is for, from its host name (ADR 0011), and its plan's limits
(Milestone 16)."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import BusinessRuleError, NotFoundError, PermissionDeniedError
from app.core.tenancy import current_tenant_id, set_tenant
from app.domain.plans import PlanLimits, can_add, limits_for
from app.domain.tenancy import slug_from_host
from app.models.enums import TenantStatus
from app.models.setup import AppUser, Location
from app.models.tenancy import Tenant


def slug_for_host(host: str | None) -> str | None:
    """acme.<BASE_DOMAIN> names "acme"; any other host names DEFAULT_TENANT_SLUG (blank on a SaaS
    server). The admin subdomain never names a company."""
    settings = get_settings()
    slug = slug_from_host(host, settings.base_domain)
    if slug is None:
        return settings.default_tenant_slug.strip().lower() or None
    if slug == settings.admin_subdomain:
        return None
    return slug


def check_open(tenant: Tenant) -> None:
    if tenant.status is TenantStatus.SUSPENDED:
        raise PermissionDeniedError(
            "This company's account is suspended. Contact Duolink support.",
            code="TENANT_SUSPENDED",
        )
    if tenant.status is TenantStatus.CANCELLED:
        raise PermissionDeniedError(
            "This company's account is closed. Contact Duolink support.", code="TENANT_CANCELLED"
        )


@dataclass(frozen=True)
class Usage:
    tenant: Tenant
    limits: PlanLimits
    users: int  # active
    locations: int  # active


def usage(db: Session) -> Usage:
    """The session's company: its plan's limits and what is in use (Milestone 16)."""
    tenant_id = current_tenant_id(db)
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFoundError("Company not found", code="TENANT_NOT_FOUND")
    users = db.execute(
        select(func.count()).where(AppUser.tenant_id == tenant_id, AppUser.is_active.is_(True))
    ).scalar_one()
    locations = db.execute(
        select(func.count()).where(Location.tenant_id == tenant_id, Location.is_active.is_(True))
    ).scalar_one()
    limits = limits_for(tenant.plan.value, tenant.max_users, tenant.max_locations)
    return Usage(tenant, limits, users, locations)


def ensure_can_add_user(db: Session) -> None:
    used = usage(db)
    if not can_add(used.users, used.limits.max_users):
        raise BusinessRuleError(
            f"Your plan allows {used.limits.max_users} active users. Deactivate one, or ask "
            "Duolink to raise the limit.",
            code="PLAN_USER_LIMIT",
        )


def ensure_can_add_location(db: Session) -> None:
    used = usage(db)
    if not can_add(used.locations, used.limits.max_locations):
        raise BusinessRuleError(
            f"Your plan allows {used.limits.max_locations} shops and godowns. Close one, or ask "
            "Duolink to raise the limit.",
            code="PLAN_LOCATION_LIMIT",
        )


def use_slug(db: Session, slug: str | None) -> Tenant:
    """For scripts run on the server: work for the company with this code (blank: the default
    company), whatever its status."""
    code = (slug or get_settings().default_tenant_slug).strip().lower()
    tenant = db.execute(select(Tenant).where(Tenant.slug == code)).scalar_one_or_none()
    if tenant is None:
        raise NotFoundError(f"No company has the code {code!r}", code="TENANT_NOT_FOUND")
    set_tenant(db, tenant.id)
    return tenant


def for_host(db: Session, host: str | None) -> Tenant:
    slug = slug_for_host(host)
    tenant = (
        db.execute(select(Tenant).where(Tenant.slug == slug)).scalar_one_or_none() if slug else None
    )
    if tenant is None:
        raise NotFoundError(
            "No company uses this address. Check the link.", code="TENANT_NOT_FOUND"
        )
    check_open(tenant)
    return tenant
