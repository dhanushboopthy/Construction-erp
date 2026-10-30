"""Shop-wide settings (one row per tenant)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.tenancy import current_tenant_id
from app.models.setup import ShopSettings
from app.models.tenancy import Tenant
from app.schemas.settings import ShopSettingsUpdate
from app.schemas.tenant import TenantOut

# One line for every shop until the owner can set their own (docs/UI_REFACTOR_PLAN.md, section 7).
DEFAULT_TAGLINE = "Bill fast. Close on time."


def get_settings_row(db: Session) -> ShopSettings:
    row = db.execute(
        select(ShopSettings).where(ShopSettings.tenant_id == current_tenant_id(db))
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Shop settings are not set up yet. Run the seed or setup wizard.")
    return row


def get_tenant(db: Session, tenant: Tenant) -> TenantOut:
    """The business name for the sign-in page and the sidebar: the trade name if there is one,
    else the legal name; the company's name until its shop settings are set up."""
    row = db.execute(
        select(ShopSettings).where(ShopSettings.tenant_id == current_tenant_id(db))
    ).scalar_one_or_none()
    return TenantOut(
        slug=tenant.slug,
        status=tenant.status,
        name=(row.trade_name or row.legal_name) if row else tenant.name,
        tagline=DEFAULT_TAGLINE,
        logo_url=(
            f"/api/v1/tenant/logo?v={row.logo_sha256[:12]}" if row and row.logo_sha256 else None
        ),
    )


def update_settings(db: Session, data: ShopSettingsUpdate) -> ShopSettings:
    row = db.execute(
        select(ShopSettings).where(ShopSettings.tenant_id == current_tenant_id(db))
    ).scalar_one_or_none()
    if row is None:
        row = ShopSettings(tenant_id=current_tenant_id(db), **data.model_dump())
        db.add(row)
    else:
        for key, value in data.model_dump().items():
            setattr(row, key, value)
    db.commit()
    return row
