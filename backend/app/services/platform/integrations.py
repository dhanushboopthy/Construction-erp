"""Duolink's GSP account and GSTIN lookup, run from the admin (Milestone 27, ADR 0013 point 7).

Credentials are encrypted at rest and never returned: an answer carries a saved key's last 4
characters at most. Usage is counted per company without request or response bodies. Only
Duolink admins call this module; the company-side lookup is `services/gstin_lookup.py`.
"""

from contextlib import suppress
from datetime import datetime

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from app.core.clock import SHOP_TZ, now_utc, today_ist
from app.core.config import get_settings
from app.core.crypto import IntegrationKeyError, decrypt_json, encrypt_json
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.domain import integrations as rules
from app.models.enums import (
    IntegrationKind,
    IntegrationOutcome,
    IntegrationProvider,
    IntegrationStatus,
    PlatformAction,
)
from app.models.integrations import IntegrationCall, PlatformIntegration
from app.models.tenancy import Tenant
from app.schemas.integrations import (
    CompanyUsageRow,
    IntegrationConnect,
    IntegrationFailureRow,
    IntegrationLimitsIn,
    IntegrationOut,
    IntegrationTestOut,
    IntegrationUsage,
    OutcomeCounts,
)
from app.services import gsp
from app.services.gsp.base import GspError
from app.services.integration_calls import integration_row, run_call
from app.services.platform import audit

FAILURES_SHOWN = 50


def _refuse(exc: rules.IntegrationRuleError) -> BusinessRuleError:
    return BusinessRuleError(exc.message, code=exc.code, field=exc.field)


def _secret_key() -> str:
    return get_settings().integration_secret_key.get_secret_value()


def _row(db: Session, kind: IntegrationKind) -> PlatformIntegration:
    row = integration_row(db, kind)
    if row is None:  # the migration seeds both
        raise NotFoundError("Integration not found")
    return row


# ------------------------------------------------------------------ status


def _source(db: Session, kind: IntegrationKind) -> tuple[str, IntegrationProvider | None]:
    """Which settings are in force: the saved ones, the GSP account's, or the environment's."""
    own = _row(db, kind)
    if own.provider is not None:
        return "database", own.provider
    if kind is IntegrationKind.GSTIN_LOOKUP:
        account = _row(db, IntegrationKind.GSP)
        if account.provider is not None:
            return "gsp_account", account.provider
    env = gsp.env_config()
    if env.provider == IntegrationProvider.FAKE.value and get_settings().is_production:
        return "none", None
    return "environment", IntegrationProvider(env.provider)


def view(db: Session, kind: IntegrationKind) -> IntegrationOut:
    row = _row(db, kind)
    source, effective = _source(db, kind)
    shown = row.provider or IntegrationProvider.SANDBOX
    status = rules.status_of(
        connected=row.provider is not None,
        last_success_at=row.last_success_at,
        last_failure_at=row.last_failure_at,
    )
    return IntegrationOut(
        kind=kind,
        provider=row.provider,
        base_url=row.base_url,
        key_last4=row.key_last4,
        status=IntegrationStatus(status),
        source=source,
        effective_provider=effective,
        credential_fields=list(rules.credential_fields(kind.value, shown.value)),
        connected_at=row.connected_at,
        last_success_at=row.last_success_at,
        last_failure_at=row.last_failure_at,
        last_failure_message=row.last_failure_message,
        daily_limit=row.daily_limit,
        monthly_limit=row.monthly_limit,
        warn_at_percent=row.warn_at_percent,
        cache_hours=row.cache_hours,
        secret_key_set=bool(_secret_key()),
    )


def list_all(db: Session) -> list[IntegrationOut]:
    return [view(db, kind) for kind in IntegrationKind]


# ------------------------------------------------------------------ changes


def connect(
    db: Session, kind: IntegrationKind, body: IntegrationConnect, admin_id: int
) -> IntegrationOut:
    row = _row(db, kind)
    provider = body.provider.value
    try:
        rules.check_provider(provider, is_production=get_settings().is_production)
        base_url = rules.check_base_url(provider, body.base_url)
        key = _secret_key()
        stored: dict[str, str] = {}
        if row.credentials and provider != IntegrationProvider.FAKE.value:
            try:
                stored = decrypt_json(row.credentials, key)
            except IntegrationKeyError as exc:
                raise ConflictError(exc.message, code=exc.code) from exc
        given = {
            name: value
            for name in rules.credential_fields(kind.value, "sandbox")
            if (value := getattr(body, name, None))
        }
        credentials = rules.merge_credentials(kind.value, provider, stored, given)
        token = None
        last4 = None
        if credentials:
            try:
                token = encrypt_json(credentials, key)
            except IntegrationKeyError as exc:
                raise ConflictError(exc.message, code=exc.code) from exc
            last4 = rules.key_last4(credentials[rules.key_field(kind.value)])
    except rules.IntegrationRuleError as exc:
        raise _refuse(exc) from exc
    row.provider = body.provider
    row.base_url = base_url
    row.credentials = token
    row.key_last4 = last4
    row.connected_at = now_utc()
    row.connected_by = admin_id
    # A fresh connection starts clean; the first test or call says whether it works.
    row.last_failure_at = None
    row.last_failure_message = None
    row.status = IntegrationStatus.CONNECTED
    audit.record(
        db,
        PlatformAction.INTEGRATION_CONNECT,
        admin_id,
        details={
            "kind": kind.value,
            "provider": provider,
            "base_url": base_url,
            "key_last4": last4,
            "fields_changed": sorted(given),
        },
    )
    db.commit()
    gsp.reset_client()
    return view(db, kind)


def disconnect(db: Session, kind: IntegrationKind, admin_id: int) -> IntegrationOut:
    row = _row(db, kind)
    if row.provider is None:
        raise ConflictError("This integration is not connected here.", code="NOT_CONNECTED")
    previous = row.provider.value
    row.provider = None
    row.base_url = ""
    row.credentials = None
    row.key_last4 = None
    row.connected_at = None
    row.connected_by = None
    row.status = IntegrationStatus.NOT_CONNECTED
    audit.record(
        db,
        PlatformAction.INTEGRATION_DISCONNECT,
        admin_id,
        details={"kind": kind.value, "provider": previous},
    )
    db.commit()
    gsp.reset_client()
    return view(db, kind)


def set_limits(
    db: Session, kind: IntegrationKind, body: IntegrationLimitsIn, admin_id: int
) -> IntegrationOut:
    row = _row(db, kind)
    new = rules.Limits(body.daily_limit, body.monthly_limit, body.warn_at_percent, body.cache_hours)
    try:
        rules.check_limits(new)
    except rules.IntegrationRuleError as exc:
        raise _refuse(exc) from exc
    old = {
        "daily_limit": row.daily_limit,
        "monthly_limit": row.monthly_limit,
        "warn_at_percent": row.warn_at_percent,
        "cache_hours": row.cache_hours,
    }
    row.daily_limit, row.monthly_limit = new.daily, new.monthly
    row.warn_at_percent, row.cache_hours = new.warn_at_percent, new.cache_hours
    audit.record(
        db,
        PlatformAction.INTEGRATION_LIMITS,
        admin_id,
        details={
            "kind": kind.value,
            "old": old,
            "new": {
                "daily_limit": new.daily,
                "monthly_limit": new.monthly,
                "warn_at_percent": new.warn_at_percent,
                "cache_hours": new.cache_hours,
            },
        },
    )
    db.commit()
    return view(db, kind)


def test_connection(db: Session, kind: IntegrationKind, admin_id: int) -> IntegrationTestOut:
    """One live call with the settings in force. A failure is an answer, not an error."""
    started = now_utc()
    ok, code, message = True, None, None
    try:
        run_call(db, kind, "test", lambda c: c.check_connection(), tenant_id=None)
    except GspError as exc:
        ok, code = False, exc.code
        secrets: tuple[str, ...] = ()
        with suppress(GspError):
            secrets = gsp.resolve(db, kind).secrets()
        message = rules.scrub(exc.message, secrets)
    latency = int((now_utc() - started).total_seconds() * 1000)
    audit.record(
        db,
        PlatformAction.INTEGRATION_TEST,
        admin_id,
        details={"kind": kind.value, "ok": ok, "error_code": code},
    )
    db.commit()
    return IntegrationTestOut(
        ok=ok,
        latency_ms=latency,
        error_code=code,
        message=message,
        integration=view(db, kind),
    )


# ------------------------------------------------------------------ usage


def _outcome_counts(db: Session, kind: IntegrationKind, since: datetime) -> OutcomeCounts:
    rows = db.execute(
        select(IntegrationCall.outcome, func.count())
        .where(IntegrationCall.kind == kind, IntegrationCall.at >= since)
        .group_by(IntegrationCall.outcome)
    ).all()
    counts = {o.value: n for o, n in rows}
    return OutcomeCounts(**counts, total=sum(counts.values()))


def usage(db: Session) -> list[IntegrationUsage]:
    windows = rules.usage_windows(today_ist(), SHOP_TZ)
    return [
        IntegrationUsage(
            kind=kind,
            today=_outcome_counts(db, kind, windows.day),
            week=_outcome_counts(db, kind, windows.week),
            month=_outcome_counts(db, kind, windows.month),
        )
        for kind in IntegrationKind
    ]


def company_usage(db: Session, kind: IntegrationKind) -> list[CompanyUsageRow]:
    row = _row(db, kind)
    windows = rules.usage_windows(today_ist(), SHOP_TZ)
    counted = IntegrationCall.outcome.in_([IntegrationOutcome.OK, IntegrationOutcome.FAILED])

    def month_count(outcome: IntegrationOutcome) -> ColumnElement[int]:
        return func.count().filter(IntegrationCall.outcome == outcome)

    rows = db.execute(
        select(
            Tenant.id,
            Tenant.slug,
            Tenant.name,
            func.count().filter(counted, IntegrationCall.at >= windows.day),
            func.count().filter(counted),
            month_count(IntegrationOutcome.CACHED),
            month_count(IntegrationOutcome.BLOCKED),
            month_count(IntegrationOutcome.FAILED),
        )
        .join(IntegrationCall, IntegrationCall.tenant_id == Tenant.id)
        .where(IntegrationCall.kind == kind, IntegrationCall.at >= windows.month)
        .group_by(Tenant.id)
        .order_by(func.count().desc(), Tenant.name)
    ).all()
    return [
        CompanyUsageRow(
            tenant_id=tid,
            slug=slug,
            name=name,
            calls_today=today,
            calls_month=month,
            cached_month=cached,
            blocked_month=blocked,
            failed_month=failed,
            near_limit=rules.near_limit(today, row.daily_limit, row.warn_at_percent)
            or rules.near_limit(month, row.monthly_limit, row.warn_at_percent),
            over_limit=today >= row.daily_limit or month >= row.monthly_limit,
        )
        for tid, slug, name, today, month, cached, blocked, failed in rows
    ]


def failures(db: Session, kind: IntegrationKind) -> list[IntegrationFailureRow]:
    rows = db.execute(
        select(IntegrationCall, Tenant.name)
        .outerjoin(Tenant, Tenant.id == IntegrationCall.tenant_id)
        .where(IntegrationCall.kind == kind, IntegrationCall.outcome == IntegrationOutcome.FAILED)
        .order_by(IntegrationCall.at.desc(), IntegrationCall.id.desc())
        .limit(FAILURES_SHOWN)
    ).all()
    return [
        IntegrationFailureRow(
            id=call.id,
            at=call.at,
            tenant_id=call.tenant_id,
            tenant_name=name,
            operation=call.operation,
            error_code=call.error_code,
            latency_ms=call.latency_ms,
        )
        for call, name in rows
    ]


# ------------------------------------------------------------------ start-up check


def refuse_to_start_without_key(db: Session) -> None:
    """Saved credentials cannot be read without the key: stop at start-up, not at the first
    e-way bill."""
    saved = db.execute(
        select(func.count())
        .select_from(PlatformIntegration)
        .where(PlatformIntegration.credentials.is_not(None))
    ).scalar_one()
    if saved and not _secret_key():
        raise RuntimeError(
            "Provider keys are saved in the database but INTEGRATION_SECRET_KEY is not set. "
            "Set the key they were saved with."
        )
