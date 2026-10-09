from fastapi import APIRouter

from app.api.deps import CurrentPrincipal, DbSession, OwnerOnly
from app.schemas.settings import ShopSettingsOut, ShopSettingsUpdate
from app.services import shop_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=ShopSettingsOut)
def get_settings(_: CurrentPrincipal, db: DbSession) -> ShopSettingsOut:
    return ShopSettingsOut.model_validate(shop_settings.get_settings_row(db))


@router.put("", response_model=ShopSettingsOut)
def put_settings(body: ShopSettingsUpdate, _: OwnerOnly, db: DbSession) -> ShopSettingsOut:
    return ShopSettingsOut.model_validate(shop_settings.update_settings(db, body))
