"""Finding the company a request is for, from its host name (ADR 0011)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFoundError, PermissionDeniedError
from app.core.tenancy import set_tenant
from app.domain.tenancy import slug_from_host
from app.models.enums import TenantStatus
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
