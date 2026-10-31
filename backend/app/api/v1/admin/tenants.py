from typing import Annotated, Literal

from fastapi import APIRouter, File, Query, Request, UploadFile, status

from app.api.deps import DbSession, PlatformAdminUser, SuperAdminOnly, request_host
from app.core.config import get_settings
from app.domain.plans import TrialState
from app.models.enums import TenantPlan, TenantStatus
from app.schemas.common import Page
from app.schemas.platform import (
    CancelRequest,
    ReactivateRequest,
    SellerDetails,
    SellerDetailsUpdate,
    SuspendRequest,
    TenantCreate,
    TenantCreated,
    TenantDetail,
    TenantRow,
    TenantUpdate,
    TenantUsage,
)
from app.services import tenant_logo
from app.services.platform import seller as seller_service
from app.services.platform import tenants as service

router = APIRouter(prefix="/tenants", tags=["admin"])


def _sign_in_url(request: Request, slug: str) -> str:
    """Where the new company's owner signs in: the slug in front of the base domain, on the
    same scheme and port the admin is using."""
    settings = get_settings()
    name, _, port = (request_host(request) or "").partition(":")
    prefix = f"{settings.admin_subdomain}."
    base = name.removeprefix(prefix) if name.startswith(prefix) else settings.base_domain
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    return f"{scheme}://{slug}.{base}" + (f":{port}" if port else "")


@router.get("", response_model=Page[TenantRow])
def list_tenants(
    _: PlatformAdminUser,
    db: DbSession,
    q: str | None = None,
    status: TenantStatus | None = None,
    plan: TenantPlan | None = None,
    trial: TrialState | None = None,
    expiring: Annotated[bool, Query(description="trial ends within 30 days")] = False,
    sort: Literal["name", "created", "last_activity", "users"] = "name",
    order: Literal["asc", "desc"] = "asc",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[TenantRow]:
    """Search by name, company code, owner or GSTIN. Filter by status, plan, trial state or
    "expiring". Sort by name, created, last activity or users."""
    rows, total = service.list_tenants(
        db,
        q=q,
        status=status,
        plan=plan,
        trial=trial,
        expiring=expiring,
        sort=sort,
        descending=order == "desc",
        limit=limit,
        offset=offset,
    )
    return Page[TenantRow](items=rows, total=total, limit=limit, offset=offset)


@router.post("", response_model=TenantCreated, status_code=status.HTTP_201_CREATED)
def create_tenant(
    body: TenantCreate, request: Request, admin: SuperAdminOnly, db: DbSession
) -> TenantCreated:
    """The whole onboarding form in one transaction: a new company with its seller details,
    first shop and godown, plan and first owner. Answers with the owner's sign-in address."""
    tenant = service.create_tenant(db, body, admin.admin_id)
    return TenantCreated(
        **service.detail(db, tenant.id).model_dump(), sign_in_url=_sign_in_url(request, tenant.slug)
    )


@router.get("/{tenant_id}", response_model=TenantDetail)
def get_tenant(tenant_id: int, _: PlatformAdminUser, db: DbSession) -> TenantDetail:
    return service.detail(db, tenant_id)


@router.get("/{tenant_id}/usage", response_model=TenantUsage)
def usage(tenant_id: int, _: PlatformAdminUser, db: DbSession) -> TenantUsage:
    """Counts only: users, shops, bills in 7, 30 and 90 days, purchases in 30 days, attachments."""
    return service.usage(db, tenant_id)


@router.patch("/{tenant_id}", response_model=TenantDetail)
def update_tenant(
    tenant_id: int, body: TenantUpdate, admin: SuperAdminOnly, db: DbSession
) -> TenantDetail:
    service.update_tenant(db, tenant_id, body, admin.admin_id)
    return service.detail(db, tenant_id)


@router.get("/{tenant_id}/seller-details", response_model=SellerDetails)
def get_seller_details(tenant_id: int, _: PlatformAdminUser, db: DbSession) -> SellerDetails:
    """What prints on the company's bills: legal name, GSTIN, PAN, CIN, address, state."""
    return seller_service.get(db, tenant_id)


@router.patch("/{tenant_id}/seller-details", response_model=SellerDetails)
def update_seller_details(
    tenant_id: int, body: SellerDetailsUpdate, admin: SuperAdminOnly, db: DbSession
) -> SellerDetails:
    """Correct the seller details for a company that cannot reach its own settings. Validated as
    the company's form is; written to the company's audit log as Duolink's and to ours with the
    old and new values. A reason is required."""
    return seller_service.update(db, tenant_id, body, admin.admin_id)


@router.post("/{tenant_id}/logo", response_model=TenantDetail)
def put_logo(
    tenant_id: int, admin: SuperAdminOnly, db: DbSession, file: Annotated[UploadFile, File()]
) -> TenantDetail:
    """Set the company's logo: a square PNG or plain SVG, up to 200 KB, checked as the owner's."""
    data = file.file.read(tenant_logo.MAX_BYTES + 1)
    service.set_logo(db, tenant_id, data, admin.admin_id)
    return service.detail(db, tenant_id)


@router.delete("/{tenant_id}/logo", response_model=TenantDetail)
def delete_logo(tenant_id: int, admin: SuperAdminOnly, db: DbSession) -> TenantDetail:
    service.remove_logo(db, tenant_id, admin.admin_id)
    return service.detail(db, tenant_id)


@router.post("/{tenant_id}/suspend", response_model=TenantDetail)
def suspend(
    tenant_id: int, body: SuspendRequest, admin: SuperAdminOnly, db: DbSession
) -> TenantDetail:
    """Everyone at the company is signed out and cannot sign in until reactivated."""
    service.suspend(db, tenant_id, body.reason, admin.admin_id)
    return service.detail(db, tenant_id)


@router.post("/{tenant_id}/cancel", response_model=TenantDetail)
def cancel(
    tenant_id: int, body: CancelRequest, admin: SuperAdminOnly, db: DbSession
) -> TenantDetail:
    """The company has left: every session ends and nobody can sign in. Its data is kept."""
    service.cancel(db, tenant_id, body.reason, admin.admin_id)
    return service.detail(db, tenant_id)


@router.post("/{tenant_id}/reactivate", response_model=TenantDetail)
def reactivate(
    tenant_id: int,
    admin: SuperAdminOnly,
    db: DbSession,
    body: ReactivateRequest | None = None,
) -> TenantDetail:
    """Undo a suspension. Reopening a cancelled company needs a reason (409 REASON_REQUIRED)."""
    service.reactivate(db, tenant_id, admin.admin_id, body.reason if body else None)
    return service.detail(db, tenant_id)
