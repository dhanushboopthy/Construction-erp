"""Every call to a shared provider goes through `run_call` (Milestone 27): it picks the settings
(the Duolink admin's saved ones, else the environment), times the call, counts it and keeps the
integration's last success or failure. Only the operation, the outcome, an error code and the
time taken are stored: never a request or a response body, and never a credential."""

from collections.abc import Callable
from time import perf_counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now_utc
from app.domain.integrations import scrub, status_of
from app.models.enums import IntegrationKind, IntegrationOutcome, IntegrationStatus
from app.models.integrations import IntegrationCall, PlatformIntegration
from app.services import gsp
from app.services.gsp.base import GspClient, GspConfig, GspError


def record(
    db: Session,
    kind: IntegrationKind,
    operation: str,
    outcome: IntegrationOutcome,
    *,
    tenant_id: int | None,
    error_code: str | None = None,
    latency_ms: int | None = None,
) -> None:
    """Add the count row to the session; it is saved with the caller's commit."""
    db.add(
        IntegrationCall(
            tenant_id=tenant_id,
            kind=kind,
            operation=operation,
            outcome=outcome,
            error_code=error_code,
            latency_ms=latency_ms,
            at=now_utc(),
        )
    )


def integration_row(db: Session, kind: IntegrationKind) -> PlatformIntegration | None:
    return db.execute(
        select(PlatformIntegration).where(PlatformIntegration.kind == kind)
    ).scalar_one_or_none()


def _note(db: Session, kind: IntegrationKind, config: GspConfig, *, failure: str | None) -> None:
    """Keep the last success or failure of the saved connection (not of the environment's)."""
    if config.source != "database":
        return
    row = integration_row(db, kind)
    if row is None or row.provider is None:
        return
    now = now_utc()
    if failure is None:
        row.last_success_at = now
    else:
        row.last_failure_at = now
        row.last_failure_message = failure
    row.status = IntegrationStatus(
        status_of(
            connected=True,
            last_success_at=row.last_success_at,
            last_failure_at=row.last_failure_at,
        )
    )


def run_call[T](
    db: Session,
    kind: IntegrationKind,
    operation: str,
    action: Callable[[GspClient], T],
    *,
    tenant_id: int | None,
) -> T:
    """Run `action` on the right provider. A failure is counted and saved at once (the caller
    saves nothing else when it fails), then raised again as the provider's GspError."""
    config = gsp.resolve(db, kind)  # may raise GspError: nothing was called, nothing is counted
    client = gsp.client_for(config)
    started = perf_counter()
    try:
        result = action(client)
    except GspError as exc:
        record(
            db,
            kind,
            operation,
            IntegrationOutcome.FAILED,
            tenant_id=tenant_id,
            error_code=exc.code,
            latency_ms=int((perf_counter() - started) * 1000),
        )
        _note(db, kind, config, failure=scrub(f"{exc.code}: {exc.message}", config.secrets()))
        db.commit()
        raise
    record(
        db,
        kind,
        operation,
        IntegrationOutcome.OK,
        tenant_id=tenant_id,
        latency_ms=int((perf_counter() - started) * 1000),
    )
    _note(db, kind, config, failure=None)
    return result
