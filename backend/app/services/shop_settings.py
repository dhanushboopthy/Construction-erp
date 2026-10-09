"""Shop-wide settings (one row per tenant)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.tenancy import TENANT_ID
from app.models.setup import ShopSettings
from app.schemas.settings import ShopSettingsUpdate


def get_settings_row(db: Session) -> ShopSettings:
    row = db.execute(
        select(ShopSettings).where(ShopSettings.tenant_id == TENANT_ID)
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Shop settings are not set up yet. Run the seed or setup wizard.")
    return row


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
