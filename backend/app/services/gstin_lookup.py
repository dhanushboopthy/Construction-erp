"""GSTIN lookup (Milestone 27): fill a party or a company form from the public registry.

A fresh answer is served from `gstin_cache` (public data shared by every company), logged
`cached`, and does not touch the provider. Over a company's daily or monthly limit the call is
refused with 429 GSTIN_LOOKUP_LIMIT and logged `blocked`. Otherwise the provider is called
through `services/gsp/` and the answer is cached. A Duolink admin's own lookup (onboarding) has
no company and no limit."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import SHOP_TZ, now_utc, today_ist
from app.core.errors import NotFoundError, TooManyRequestsError, UpstreamError
from app.domain import integrations as rules
from app.models.enums import IntegrationKind, IntegrationOutcome
from app.models.integrations import GstinCache, IntegrationCall
from app.schemas.integrations import GstinLookupOut
from app.services.gsp.base import GspError, TaxpayerInfo
from app.services.integration_calls import integration_row, record, run_call

OPERATION = "lookup_gstin"
LIMIT_CODE = "GSTIN_LOOKUP_LIMIT"


def _used(db: Session, tenant_id: int) -> tuple[int, int]:
    """Provider calls (ok and failed) this company made today and this month."""
    windows = rules.usage_windows(today_ist(), SHOP_TZ)
    counted = IntegrationCall.outcome.in_([IntegrationOutcome.OK, IntegrationOutcome.FAILED])
    today, month = db.execute(
        select(
            func.count().filter(IntegrationCall.at >= windows.day),
            func.count(),
        ).where(
            IntegrationCall.tenant_id == tenant_id,
            IntegrationCall.kind == IntegrationKind.GSTIN_LOOKUP,
            IntegrationCall.at >= windows.month,
            counted,
        )
    ).one()
    return today, month


def _out(
    cache: GstinCache, *, cached: bool, limits: rules.Limits, used_today: int, company: bool
) -> GstinLookupOut:
    return GstinLookupOut(
        gstin=cache.gstin,
        legal_name=cache.legal_name,
        trade_name=cache.trade_name,
        address=cache.address,
        state_code=cache.state_code,
        status=cache.status,
        fetched_at=cache.fetched_at,
        cached=cached,
        lookups_left_today=rules.remaining(used_today, limits.daily) if company else None,
        near_limit=company and rules.near_limit(used_today, limits.daily, limits.warn_at_percent),
    )


def _store(db: Session, found: TaxpayerInfo) -> GstinCache:
    row = db.get(GstinCache, found.gstin)
    if row is None:
        row = GstinCache(gstin=found.gstin)
        db.add(row)
    row.legal_name = found.legal_name
    row.trade_name = found.trade_name
    row.address = found.address
    row.state_code = found.state_code
    row.status = found.status
    row.fetched_at = now_utc()
    return row


def lookup(db: Session, gstin: str, *, tenant_id: int | None) -> GstinLookupOut:
    settings = integration_row(db, IntegrationKind.GSTIN_LOOKUP)
    if settings is None:  # the migration seeds it
        raise NotFoundError("The GSTIN lookup is not set up")
    limits = rules.Limits(
        settings.daily_limit,
        settings.monthly_limit,
        settings.warn_at_percent,
        settings.cache_hours,
    )
    company = tenant_id is not None
    used_today, used_month = _used(db, tenant_id) if tenant_id is not None else (0, 0)
    cache = db.get(GstinCache, gstin)
    fresh = cache is not None and rules.is_fresh(cache.fetched_at, now_utc(), limits.cache_hours)
    # A Duolink admin has no company allowance to spend.
    decision = rules.lookup_decision(
        fresh=fresh,
        used_today=used_today if company else 0,
        used_month=used_month if company else 0,
        limits=limits,
    )
    kind = IntegrationKind.GSTIN_LOOKUP
    if decision == "cached" and cache is not None:
        record(db, kind, OPERATION, IntegrationOutcome.CACHED, tenant_id=tenant_id)
        db.commit()
        return _out(cache, cached=True, limits=limits, used_today=used_today, company=company)
    if decision == "blocked":
        record(
            db,
            kind,
            OPERATION,
            IntegrationOutcome.BLOCKED,
            tenant_id=tenant_id,
            error_code=LIMIT_CODE,
        )
        db.commit()
        raise TooManyRequestsError(
            "Your company has used its GSTIN lookups for now. Type the details in, or try again "
            "tomorrow.",
            code=LIMIT_CODE,
        )
    try:
        found = run_call(db, kind, OPERATION, lambda c: c.lookup_gstin(gstin), tenant_id=tenant_id)
    except GspError as exc:
        raise UpstreamError(
            exc.message + (" Try again in a minute." if exc.retryable else ""), code=exc.code
        ) from exc
    row = _store(db, found)
    db.commit()
    return _out(row, cached=False, limits=limits, used_today=used_today + 1, company=company)
