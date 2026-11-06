"""Duolink's GSP account and GSTIN lookup (Milestone 27, ADR 0013 point 7).

Support admins read the status (is it working?) and nothing else here; changing a credential or
a quota is a commercial decision, and usage is a Super Admin's view. No answer carries a
credential: a saved key shows as its last 4 characters. Counts only, never a request or a
response body."""

from fastapi import APIRouter

from app.api.deps import DbSession, PlatformAdminUser, SuperAdminOnly
from app.models.enums import IntegrationKind, PlatformAction
from app.schemas.integrations import (
    CompanyUsageRow,
    GstinLookupIn,
    GstinLookupOut,
    IntegrationConnect,
    IntegrationFailureRow,
    IntegrationLimitsIn,
    IntegrationOut,
    IntegrationTestOut,
    IntegrationUsage,
)
from app.services import gstin_lookup
from app.services.platform import audit
from app.services.platform import integrations as service

router = APIRouter(prefix="/integrations", tags=["admin"])


@router.get("", response_model=list[IntegrationOut])
def status(_: PlatformAdminUser, db: DbSession) -> list[IntegrationOut]:
    """The GSP and the GSTIN lookup: connected or not, which settings are in force (saved
    here, the GSP account's, or the environment's) and the last success and failure."""
    return service.list_all(db)


@router.get("/usage", response_model=list[IntegrationUsage])
def usage(_: SuperAdminOnly, db: DbSession) -> list[IntegrationUsage]:
    """Calls today, this week and this month by outcome (ok, failed, cached, blocked)."""
    return service.usage(db)


@router.post("/gstin-lookup", response_model=GstinLookupOut)
def lookup(body: GstinLookupIn, admin: SuperAdminOnly, db: DbSession) -> GstinLookupOut:
    """Fill the onboarding form from the registry. No company limit applies. 502 when the
    provider fails."""
    found = gstin_lookup.lookup(db, body.gstin, tenant_id=None)
    audit.record(db, PlatformAction.GSTIN_LOOKUP, admin.admin_id, details={"gstin": body.gstin})
    db.commit()
    return found


@router.put("/{kind}", response_model=IntegrationOut)
def connect(
    kind: IntegrationKind, body: IntegrationConnect, admin: SuperAdminOnly, db: DbSession
) -> IntegrationOut:
    """Connect or update. A credential left blank keeps the saved one. 409 for a missing or
    wrong INTEGRATION_SECRET_KEY, the pretend provider in production, or incomplete
    credentials."""
    return service.connect(db, kind, body, admin.admin_id)


@router.post("/{kind}/test", response_model=IntegrationTestOut)
def test_connection(
    kind: IntegrationKind, admin: SuperAdminOnly, db: DbSession
) -> IntegrationTestOut:
    """One live call with the settings in force. A failure is a 200 with `ok: false`."""
    return service.test_connection(db, kind, admin.admin_id)


@router.post("/{kind}/disconnect", response_model=IntegrationOut)
def disconnect(kind: IntegrationKind, admin: SuperAdminOnly, db: DbSession) -> IntegrationOut:
    """Forget the saved credentials; the environment becomes the fallback again."""
    return service.disconnect(db, kind, admin.admin_id)


@router.patch("/{kind}/limits", response_model=IntegrationOut)
def update_limits(
    kind: IntegrationKind, body: IntegrationLimitsIn, admin: SuperAdminOnly, db: DbSession
) -> IntegrationOut:
    """Per company: calls a day and a month, when to warn, and the GSTIN cache hours. Only the
    GSTIN lookup refuses a company over its limit; a bill is never held back by the GSP limit."""
    return service.set_limits(db, kind, body, admin.admin_id)


@router.get("/{kind}/companies", response_model=list[CompanyUsageRow])
def company_usage(kind: IntegrationKind, _: SuperAdminOnly, db: DbSession) -> list[CompanyUsageRow]:
    return service.company_usage(db, kind)


@router.get("/{kind}/failures", response_model=list[IntegrationFailureRow])
def recent_failures(
    kind: IntegrationKind, _: SuperAdminOnly, db: DbSession
) -> list[IntegrationFailureRow]:
    """The last failed calls: operation, error code, company. No bodies."""
    return service.failures(db, kind)
