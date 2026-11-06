from typing import Annotated

from fastapi import APIRouter, File, Response, UploadFile
from fastapi.responses import JSONResponse

from app.api.deps import CurrentTenant, DbSession, OwnerOnly
from app.schemas.platform import TenantPlanOut
from app.schemas.tenant import TenantOut
from app.services import app_manifest, shop_settings, tenant_logo
from app.services import tenants as tenant_service

router = APIRouter(prefix="/tenant", tags=["tenant"])
MANIFEST_TYPE = "application/manifest+json"


@router.get("", response_model=TenantOut)
def get_tenant(tenant: CurrentTenant, db: DbSession) -> TenantOut:
    """The company this address belongs to (ADR 0011): its address name, status, business name,
    tagline and logo address, so the sign-in page and the app shell can show whose shop this is.
    Open to anyone: it is the name printed on every bill, and nothing else from the settings (bank
    details, thresholds) is ever added here. 404 TENANT_NOT_FOUND for an unknown address; 403
    TENANT_SUSPENDED or TENANT_CANCELLED for a closed account."""
    return shop_settings.get_tenant(db, tenant)


@router.get(
    "/manifest.webmanifest",
    response_class=JSONResponse,
    responses={200: {"content": {MANIFEST_TYPE: {}}}},
)
def get_manifest(tenant: CurrentTenant, db: DbSession) -> JSONResponse:
    """The web app manifest (Milestone 29): the company's name and logo, so the ERP installs on
    the shop's PC or phone as that shop's app. Open, like the name: the browser fetches it
    without signing in. Never cached by the service worker (nothing under /api is)."""
    return JSONResponse(
        app_manifest.manifest(db, tenant),
        media_type=MANIFEST_TYPE,
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/plan", response_model=TenantPlanOut)
def plan(_: OwnerOnly, db: DbSession) -> TenantPlanOut:
    """The company's plan and how much of it is in use (Settings, Users)."""
    used = tenant_service.usage(db)
    return TenantPlanOut(
        plan=used.tenant.plan.code,
        plan_name=used.tenant.plan.name,
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
