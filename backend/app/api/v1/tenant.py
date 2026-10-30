from typing import Annotated

from fastapi import APIRouter, File, Response, UploadFile

from app.api.deps import DbSession, OwnerOnly
from app.schemas.tenant import TenantOut
from app.services import shop_settings, tenant_logo

router = APIRouter(prefix="/tenant", tags=["tenant"])


@router.get("", response_model=TenantOut)
def get_tenant(db: DbSession) -> TenantOut:
    """Name, tagline and logo address only, so the sign-in page and the app shell can show whose
    shop this is. Open to anyone: it is the name printed on every bill, and nothing else from the
    settings (bank details, thresholds) is ever added here."""
    return shop_settings.get_tenant(db)


@router.get("/logo", response_class=Response)
def get_logo(db: DbSession) -> Response:
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
def put_logo(_: OwnerOnly, db: DbSession, file: Annotated[UploadFile, File()]) -> TenantOut:
    """Replace the logo (owner only): a square PNG or plain SVG, up to 200 KB."""
    data = file.file.read(tenant_logo.MAX_BYTES + 1)  # one byte more, so a big file is noticed
    tenant_logo.save(db, data)
    return shop_settings.get_tenant(db)


@router.delete("/logo", response_model=TenantOut)
def delete_logo(_: OwnerOnly, db: DbSession) -> TenantOut:
    """Go back to the initials tile (owner only)."""
    tenant_logo.remove(db)
    return shop_settings.get_tenant(db)
