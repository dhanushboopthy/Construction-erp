from typing import Annotated

from fastapi import APIRouter, File, Response, UploadFile

from app.api.deps import CurrentTenant, DbSession, OwnerOnly
from app.schemas.platform import TenantPlanOut
from app.schemas.tenant import TenantOut
from app.services import shop_settings, tenant_logo
from app.services import tenants as tenant_service

router = APIRouter(prefix="/tenant", tags=["tenant"])


@router.get("", response_model=TenantOut)
def get_tenant(tenant: CurrentTenant, db: DbSession) -> TenantOut:
    """The company this address belongs to (ADR 0011): its address name, status, business name,
    tagline and logo address, so the sign-in page and the app shell can show whose shop this is.
    Open to anyone: it is the name printed on every bill, and nothing else from the settings (bank
    details, thresholds) is ever added here. 404 TENANT_NOT_FOUND for an unknown address; 403
    TENANT_SUSPENDED or TENANT_CANCELLED for a closed account."""
    return shop_settings.get_tenant(db, tenant)


@router.get("/plan", response_model=TenantPlanOut)
def plan(_: OwnerOnly, db: DbSession) -> TenantPlanOut:
    """The company's plan and how much of it is in use (Settings, Users)."""
    used = tenant_service.usage(db)
    return TenantPlanOut(
        plan=used.tenant.plan,
        status=used.tenant.status,
        trial_ends_at=used.tenant.trial_ends_at,
        users=used.users,
        max_users=used.limits.max_users,
        locations=used.locations,
        max_locations=used.limits.max_locations,
    )


@router.get("/logo", response_class=Response)
def get_logo(_: CurrentTenant, db: DbSession) -> Response:
    """The logo image. Open for the same reason as the name: the sign-in page shows it. Served so
    a browser can only draw it: no sniffing, and a policy that forbids scripts and sub-resources."""
    data, content_type, digest = tenant_logo.read(db)
    return Response(
        data,
        media_type=content_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
            "Cache-Control": "public, max-age=86400",
            "ETag": f'"{digest[:12]}"',
        },
    )


@router.put("/logo", response_model=TenantOut)
def put_logo(
    _: OwnerOnly, tenant: CurrentTenant, db: DbSession, file: Annotated[UploadFile, File()]
) -> TenantOut:
    """Replace the logo (owner only): a square PNG or plain SVG, up to 200 KB."""
    data = file.file.read(tenant_logo.MAX_BYTES + 1)  # one byte more, so a big file is noticed
    tenant_logo.save(db, data)
    return shop_settings.get_tenant(db, tenant)


@router.delete("/logo", response_model=TenantOut)
def delete_logo(_: OwnerOnly, tenant: CurrentTenant, db: DbSession) -> TenantOut:
    """Go back to the initials tile (owner only)."""
    tenant_logo.remove(db)
    return shop_settings.get_tenant(db, tenant)
