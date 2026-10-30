"""Shop-wide settings (one row per tenant)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.tenancy import TENANT_ID
from app.models.setup import ShopSettings
from app.schemas.settings import ShopSettingsUpdate
from app.schemas.tenant import TenantOut

# One line for every shop until the owner can set their own (docs/UI_REFACTOR_PLAN.md, section 7).
DEFAULT_TAGLINE = "Bill fast. Close on time."


def get_settings_row(db: Session) -> ShopSettings:
    row = db.execute(
        select(ShopSettings).where(ShopSettings.tenant_id == TENANT_ID)
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Shop settings are not set up yet. Run the seed or setup wizard.")
    return row


def get_tenant(db: Session) -> TenantOut:
    """The business name for the sidebar: the trade name if there is one, else the legal name."""
    row = get_settings_row(db)
    return TenantOut(name=row.trade_name or row.legal_name, tagline=DEFAULT_TAGLINE)


def update_settings(db: Session, data: ShopSettingsUpdate) -> ShopSettings:
    row = db.execute(
        select(ShopSettings).where(ShopSettings.tenant_id == TENANT_ID)
    ).scalar_one_or_none()
    if row is None:
        row = ShopSettings(tenant_id=TENANT_ID, **data.model_dump())
        db.add(row)
    else:
        for key, value in data.model_dump().items():
            setattr(row, key, value)
    db.commit()
    return row
