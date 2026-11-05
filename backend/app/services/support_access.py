"""Owner-granted support access, as the company sees it, and the support session gate
(Milestone 23, ADR 0013).

The owner grants Duolink access for 1, 4, 24 or 72 hours, sees the live grant and revokes it at
any time. A Super Admin then enters the company with a "support" token
(`services/platform/support_access.py`). Every request under that token passes `authenticate`:

1. the token must be for this company, its session open, its grant live and its admin still an
   active Super Admin, or the request answers 401 (so a revoke bites on the next request);
2. the method and path (never a body or query string) are logged and the session's request
   count goes up, in their own transaction;
3. anything but a read, or leaving the session, answers 403 SUPPORT_READ_ONLY;
4. the database session is then marked read-only: any flush or INSERT/UPDATE/DELETE through it
   raises SUPPORT_READ_ONLY too, so a GET that would write on the side cannot.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import event, func, select, update
from sqlalchemy.orm import ORMExecuteState, Session, UOWTransaction

from app.core.clock import now_utc
from app.core.context import request_id_var
from app.core.errors import (
    AuthenticationError,
    BusinessRuleError,
    NotFoundError,
    PermissionDeniedError,
)
from app.core.security import SupportClaims
from app.core.tenancy import current_tenant_id
from app.domain import support_access as rules
from app.models.enums import AuditAction, PlatformAction, PlatformRole, SupportSessionEnd
from app.models.platform import PlatformAdmin
from app.models.setup import AppUser
from app.models.support import SupportTicket
from app.models.support_access import SupportAccessGrant, SupportSession, SupportSessionEvent
from app.models.tenancy import Tenant
from app.schemas.support_access import (
    AccessOverview,
    GrantCreate,
    GrantOut,
    GrantStatus,
    SessionEventOut,
    SessionRow,
    SessionStatus,
    SupportSessionStatus,
)
from app.services.audit import record_event
from app.services.platform.audit import record as record_platform

READ_ONLY_KEY = "support_read_only"
LOCK_CLASS = 23  # pg_advisory_xact_lock(23, tenant_id): one grant change per company at a time
RECENT_GRANTS = 10
HISTORY_LIMIT = 100
READ_ONLY_MESSAGE = "This is a read-only Duolink support session. Nothing can be saved."
ENDED_MESSAGE = "This Duolink support session has ended. Enter the company again from the admin."

_END_FOR: dict[rules.Refusal, SupportSessionEnd] = {
    rules.Refusal.GRANT_REVOKED: SupportSessionEnd.REVOKED,
    rules.Refusal.GRANT_ENDED: SupportSessionEnd.GRANT_ENDED,
    rules.Refusal.ADMIN_NOT_ALLOWED: SupportSessionEnd.ADMIN_NOT_ALLOWED,
}


def read_only_error() -> PermissionDeniedError:
    return PermissionDeniedError(READ_ONLY_MESSAGE, code="SUPPORT_READ_ONLY")


# ---------------------------------------------------------------- the read-only session guard


def _this_request() -> str:
    return request_id_var.get() or "no-request"


def make_read_only(db: Session) -> None:
    """For the rest of this request the database session writes nothing (a support request,
    once its event is logged). The mark names the request, so it can never outlive it."""
    db.info[READ_ONLY_KEY] = _this_request()


def clear_read_only(db: Session) -> None:
    db.info.pop(READ_ONLY_KEY, None)


def _is_read_only(session: Session) -> bool:
    mark = session.info.get(READ_ONLY_KEY)
    return mark is not None and mark == _this_request()


@event.listens_for(Session, "before_flush")
def _refuse_flush(session: Session, _ctx: UOWTransaction, _instances: object) -> None:
    if _is_read_only(session) and (session.new or session.dirty or session.deleted):
        raise read_only_error()


@event.listens_for(Session, "do_orm_execute")
def _refuse_statement(state: ORMExecuteState) -> None:
    if _is_read_only(state.session) and (state.is_insert or state.is_update or state.is_delete):
        raise read_only_error()


# ---------------------------------------------------------------- the support principal


@dataclass(frozen=True)
class SupportContext:
    """A live support session, as one request sees it."""

    session_id: int
    grant_id: int
    admin_id: int
    admin_name: str
    include_costs: bool
    started_at: datetime
    expires_at: datetime
    grant_ends_at: datetime


def _admin_may_enter(admin: PlatformAdmin | None) -> bool:
    return admin is not None and admin.is_active and admin.role is PlatformRole.SUPER_ADMIN


def authenticate(
    db: Session, tenant: Tenant, claims: SupportClaims, method: str, path: str
) -> SupportContext:
    """Check, log and gate one request under a support token. See the module docstring."""
    now = now_utc()
    if claims.tenant_id != tenant.id:
        # A token for another company: refused before anything of this one is read.
        raise AuthenticationError("Sign in to continue")
    session = db.get(SupportSession, claims.session_id)
    if session is not None and (
        session.tenant_id != tenant.id
        or session.grant_id != claims.grant_id
        or session.admin_id != claims.admin_id
    ):
        session = None
    grant = db.get(SupportAccessGrant, session.grant_id) if session is not None else None
    admin = db.get(PlatformAdmin, claims.admin_id)
    state = (
        rules.grant_state(grant.starts_at, grant.ends_at, grant.revoked_at, now)
        if grant is not None
        else rules.GrantState.ENDED
    )
    refused = rules.refusal(
        token_tenant_id=claims.tenant_id,
        tenant_id=tenant.id,
        session_found=session is not None,
        session_ended=session is not None and session.ended_at is not None,
        grant_state=state,
        admin_may_enter=_admin_may_enter(admin),
    )
    if refused is not None:
        if session is not None and refused.ends_session:
            end_session(db, session, _END_FOR[refused], now, user_id=None)
            db.commit()
        raise AuthenticationError(ENDED_MESSAGE, code="SUPPORT_SESSION_ENDED")
    assert session is not None  # noqa: S101 - refusal() returned None, so all three exist
    assert grant is not None  # noqa: S101
    assert admin is not None  # noqa: S101

    allowed = rules.support_may(method, path)
    db.add(
        SupportSessionEvent(
            tenant_id=tenant.id,
            session_id=session.id,
            at=now,
            method=method[:8],
            path=path[:300],
            refused=not allowed,
        )
    )
    db.execute(
        update(SupportSession)
        .where(SupportSession.id == session.id)
        .values(request_count=SupportSession.request_count + 1)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    if not allowed:
        raise read_only_error()
    return SupportContext(
        session_id=session.id,
        grant_id=grant.id,
        admin_id=admin.id,
        admin_name=admin.full_name,
        include_costs=grant.include_costs,
        started_at=session.started_at,
        expires_at=session.expires_at,
        grant_ends_at=grant.ends_at,
    )


def end_session(
    db: Session,
    session: SupportSession,
    reason: SupportSessionEnd,
    now: datetime,
    *,
    user_id: int | None,
) -> None:
    """Close the session and say so in both audit logs. A session whose token had already run
    out ends when it ran out, not now. The caller commits."""
    session.ended_at = min(now, session.expires_at)
    session.end_reason = reason
    details = {"session_id": session.id, "reason": reason.value}
    record_event(
        db,
        AuditAction.SUPPORT_EXIT,
        "support_session",
        session.id,
        {**details, "admin_id": session.admin_id},
        user_id=user_id,
    )
    record_platform(
        db,
        PlatformAction.SUPPORT_SESSION_END,
        session.admin_id,
        tenant_id=session.tenant_id,
        details=details,
    )


def exit_session(db: Session, ctx: SupportContext) -> None:
    """The admin leaves. The token is useless from the next request on."""
    session = db.get(SupportSession, ctx.session_id)
    if session is not None and session.ended_at is None:
        end_session(db, session, SupportSessionEnd.EXITED, now_utc(), user_id=None)
        db.commit()


def status(db: Session, tenant: Tenant, ctx: SupportContext) -> SupportSessionStatus:
    return SupportSessionStatus(
        session_id=ctx.session_id,
        company_name=tenant.name,
        admin_name=ctx.admin_name,
        started_at=ctx.started_at,
        expires_at=ctx.expires_at,
        grant_ends_at=ctx.grant_ends_at,
        include_costs=ctx.include_costs,
    )


# ---------------------------------------------------------------- the owner's Settings


def _names(db: Session, ids: Iterable[int | None]) -> dict[int, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = db.execute(select(AppUser.id, AppUser.full_name).where(AppUser.id.in_(wanted)))
    return {row.id: row.full_name for row in rows}


def _ticket_numbers(db: Session, ids: Iterable[int | None]) -> dict[int, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = db.execute(
        select(SupportTicket.id, SupportTicket.number).where(SupportTicket.id.in_(wanted))
    )
    return {row.id: row.number for row in rows}


def _grant_status(grant: SupportAccessGrant, now: datetime) -> GrantStatus:
    state = rules.grant_state(grant.starts_at, grant.ends_at, grant.revoked_at, now)
    if state is rules.GrantState.LIVE:
        return "live"
    return "revoked" if state is rules.GrantState.REVOKED else "ended"


def _grant_out(
    grant: SupportAccessGrant, now: datetime, names: dict[int, str], tickets: dict[int, str]
) -> GrantOut:
    state = _grant_status(grant, now)
    return GrantOut(
        id=grant.id,
        status=state,
        starts_at=grant.starts_at,
        ends_at=grant.ends_at,
        seconds_left=rules.seconds_left(grant.ends_at, now) if state == "live" else 0,
        include_costs=grant.include_costs,
        reason=grant.reason,
        ticket_id=grant.ticket_id,
        ticket_number=tickets.get(grant.ticket_id) if grant.ticket_id else None,
        granted_by_name=names.get(grant.granted_by_user_id, "—"),
        revoked_at=grant.revoked_at,
        revoked_by_name=names.get(grant.revoked_by_user_id) if grant.revoked_by_user_id else None,
    )


def _grants_out(db: Session, grants: list[SupportAccessGrant], now: datetime) -> list[GrantOut]:
    names = _names(
        db, [g.granted_by_user_id for g in grants] + [g.revoked_by_user_id for g in grants]
    )
    tickets = _ticket_numbers(db, [g.ticket_id for g in grants])
    return [_grant_out(g, now, names, tickets) for g in grants]


def live_grant(db: Session, now: datetime) -> SupportAccessGrant | None:
    return db.execute(
        select(SupportAccessGrant)
        .where(
            SupportAccessGrant.tenant_id == current_tenant_id(db),
            SupportAccessGrant.revoked_at.is_(None),
            SupportAccessGrant.starts_at <= now,
            SupportAccessGrant.ends_at > now,
        )
        .order_by(SupportAccessGrant.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def overview(db: Session) -> AccessOverview:
    now = now_utc()
    recent = list(
        db.execute(
            select(SupportAccessGrant)
            .where(SupportAccessGrant.tenant_id == current_tenant_id(db))
            .order_by(SupportAccessGrant.id.desc())
            .limit(RECENT_GRANTS)
        ).scalars()
    )
    rows = _grants_out(db, recent, now)
    live = next((r for r in rows if r.status == "live"), None)
    return AccessOverview(live=live, recent=rows, durations=list(rules.GRANT_HOURS))


def _lock(db: Session) -> None:
    db.execute(select(func.pg_advisory_xact_lock(LOCK_CLASS, current_tenant_id(db))))


def _end_open_sessions(db: Session, grant: SupportAccessGrant, now: datetime, owner_id: int) -> int:
    sessions = db.execute(
        select(SupportSession).where(
            SupportSession.tenant_id == current_tenant_id(db),
            SupportSession.grant_id == grant.id,
            SupportSession.ended_at.is_(None),
        )
    ).scalars()
    ended = 0
    for session in sessions:
        end_session(db, session, SupportSessionEnd.REVOKED, now, user_id=owner_id)
        ended += 1
    return ended


def _revoke_live(db: Session, owner_id: int, now: datetime) -> list[SupportAccessGrant]:
    revoked = list(
        db.execute(
            select(SupportAccessGrant).where(
                SupportAccessGrant.tenant_id == current_tenant_id(db),
                SupportAccessGrant.revoked_at.is_(None),
                SupportAccessGrant.ends_at > now,
            )
        ).scalars()
    )
    for grant in revoked:
        grant.revoked_at = now
        grant.revoked_by_user_id = owner_id
        _end_open_sessions(db, grant, now, owner_id)
    return revoked


def grant(db: Session, owner_id: int, data: GrantCreate) -> GrantOut:
    """A new grant replaces the live one, which is recorded as revoked (and its sessions end)."""
    now = now_utc()
    try:
        starts, ends = rules.grant_window(now, data.duration_hours)
    except rules.SupportAccessError as exc:  # pragma: no cover - the schema allows only these
        raise BusinessRuleError(str(exc), code=exc.code) from exc
    if data.ticket_id is not None:
        ticket = db.get(SupportTicket, data.ticket_id)
        if ticket is None or ticket.tenant_id != current_tenant_id(db):
            raise NotFoundError("No such ticket.", code="TICKET_NOT_FOUND", field="ticket_id")
    _lock(db)
    _revoke_live(db, owner_id, now)
    row = SupportAccessGrant(
        tenant_id=current_tenant_id(db),
        granted_by_user_id=owner_id,
        starts_at=starts,
        ends_at=ends,
        include_costs=data.include_costs,
        reason=data.reason.strip(),
        ticket_id=data.ticket_id,
    )
    db.add(row)
    db.commit()
    return _grants_out(db, [row], now)[0]


def revoke(db: Session, owner_id: int) -> GrantOut:
    """End the live grant now; any Duolink session under it is refused from its next request.
    409 NO_LIVE_GRANT when there is none."""
    now = now_utc()
    _lock(db)
    revoked = _revoke_live(db, owner_id, now)
    if not revoked:
        raise BusinessRuleError("Duolink has no support access to revoke.", code="NO_LIVE_GRANT")
    db.commit()
    return _grants_out(db, revoked[-1:], now)[0]


def session_status(session: SupportSession, now: datetime) -> SessionStatus:
    if rules.session_is_open(session.ended_at, session.expires_at, now):
        return "open"
    return "stale" if rules.session_is_stale(session.ended_at, session.expires_at, now) else "ended"


def history(db: Session) -> list[SessionRow]:
    """Who from Duolink entered, when, for how long and how many requests they made."""
    now = now_utc()
    rows = db.execute(
        select(SupportSession, PlatformAdmin.full_name, SupportAccessGrant.include_costs)
        .join(PlatformAdmin, PlatformAdmin.id == SupportSession.admin_id)
        .join(SupportAccessGrant, SupportAccessGrant.id == SupportSession.grant_id)
        .where(SupportSession.tenant_id == current_tenant_id(db))
        .order_by(SupportSession.started_at.desc(), SupportSession.id.desc())
        .limit(HISTORY_LIMIT)
    ).all()
    return [
        SessionRow(
            id=s.id,
            grant_id=s.grant_id,
            admin_name=admin_name,
            reason=s.reason,
            status=session_status(s, now),
            started_at=s.started_at,
            ended_at=rules.effective_end(s.ended_at, s.expires_at, now),
            end_reason=s.end_reason,
            request_count=s.request_count,
            include_costs=include_costs,
        )
        for s, admin_name, include_costs in rows
    ]


def session_events(db: Session, session_id: int) -> list[SessionEventOut]:
    """Every request of one session, oldest first: method and path only."""
    session = db.get(SupportSession, session_id)
    if session is None or session.tenant_id != current_tenant_id(db):
        raise NotFoundError("No such support session.", code="SUPPORT_SESSION_NOT_FOUND")
    rows = db.execute(
        select(SupportSessionEvent)
        .where(
            SupportSessionEvent.tenant_id == current_tenant_id(db),
            SupportSessionEvent.session_id == session.id,
        )
        .order_by(SupportSessionEvent.id)
    ).scalars()
    return [SessionEventOut(at=e.at, method=e.method, path=e.path, refused=e.refused) for e in rows]
