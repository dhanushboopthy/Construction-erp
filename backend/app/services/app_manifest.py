"""The web app manifest a company's address serves (Milestone 29): the company's name and logo,
so the ERP installs on the shop's PC or phone as that shop's app."""

from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domain import pwa
from app.models.tenancy import Tenant
from app.services import shop_settings, tenant_logo


def manifest(db: Session, tenant: Tenant) -> dict[str, Any]:
    """Its logo is the first icon when the file can be read and its size known; the Duolink
    mark is always there as well."""
    shown = shop_settings.get_tenant(db, tenant)
    logo = None
    if shown.logo_url:
        try:
            data, content_type, _ = tenant_logo.read(db)
        except AppError:  # missing or damaged in storage: the Duolink mark stands in
            data, content_type = b"", ""
        logo = pwa.logo_icon(shown.logo_url, content_type, data[:24])
    return pwa.manifest(shown.name, logo)
