"""The seller's legal details, corrected by Duolink for a company that cannot get into its own
settings (Milestone 18): legal name, GSTIN, PAN, CIN, address and state.

The change goes through the same service as the company's Settings screen, inside that company's
tenant context, so it is validated the same way, stamped with the right company and written to
the company's own audit log (as "Duolink: <admin>"). The platform audit log gets the old and
new values and the reason."""

from typing import Any

from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.tenancy import tenant_context
from app.models.enums import PlatformAction
from app.models.setup import ShopSettings
from app.schemas.platform import SellerDetails, SellerDetailsUpdate
from app.schemas.settings import ShopSettingsUpdate
from app.services import shop_settings
from app.services.platform.audit import record
from app.services.platform.tenants import get_tenant

# API name -> settings column. The API calls the GSTIN `registration_no` (admin answers keep
# clear of money-like names, see test_platform_admin).
FIELDS = {
    "legal_name": "legal_name",
    "registration_no": "gstin",
    "pan": "pan",
    "cin": "cin",
    "address": "address",
    "state_code": "state_code",
}
NOT_BLANK = frozenset({"legal_name", "address", "state_code"})


def _details(row: ShopSettings) -> SellerDetails:
    return SellerDetails(
        legal_name=row.legal_name,
        registration_no=row.gstin,
        pan=row.pan,
        cin=row.cin,
        address=row.address,
        state_code=row.state_code,
    )


def get(db: Session, tenant_id: int) -> SellerDetails:
    tenant = get_tenant(db, tenant_id)
    with tenant_context(db, tenant.id):
        return _details(shop_settings.get_settings_row(db))


def update(db: Session, tenant_id: int, body: SellerDetailsUpdate, admin_id: int) -> SellerDetails:
    tenant = get_tenant(db, tenant_id)
    with tenant_context(db, tenant.id):
        row = shop_settings.get_settings_row(db)
        current = {name: getattr(row, name) for name in ShopSettingsUpdate.model_fields}
        patch: dict[str, Any] = {}
        for api_name, column in FIELDS.items():
            if api_name not in body.model_fields_set:
                continue
            value = getattr(body, api_name)
            if value is None and api_name in NOT_BLANK:
                continue  # these cannot be cleared
            patch[column] = value
        try:
            valid = ShopSettingsUpdate.model_validate({**current, **patch})
        except ValidationError as exc:
            raise RequestValidationError(exc.errors()) from exc

        changes = {
            api_name: {"from": current[column], "to": getattr(valid, column)}
            for api_name, column in FIELDS.items()
            if column in patch and current[column] != getattr(valid, column)
        }
        if changes:
            record(
                db,
                PlatformAction.TENANT_SELLER_UPDATE,
                admin_id,
                tenant_id=tenant.id,
                details={"changes": changes, "reason": body.reason},
            )
            row = shop_settings.update_settings(db, valid)  # commits, with the audit row
        return _details(row)
