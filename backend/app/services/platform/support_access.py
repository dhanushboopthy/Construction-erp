"""Entering a company with its owner's consent, from the admin (Milestone 23, ADR 0013).

A Super Admin opens a support session only while the company's owner has a live grant. The
session row is written in the company's tenant context, so it is the company's own row and its
audit log says "Duolink: <admin>" entered. The token is a "support" token: it lasts two hours at
most, never past the grant, and works only at that company's address, read-only. Everything
here answers statuses, times and counts, never a figure from the company's books.
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now_utc
from app.core.errors import BusinessRuleError
from app.core.security import SupportClaims, create_support_token
from app.core.tenancy import tenant_context
from app.domain import support_access as rules
from app.models.enums import AuditAction, PlatformAction, SupportSessionEnd, TenantStatus
from app.models.platform import PlatformAdmin
from app.models.setup import AppUser
from app.models.support import SupportTicket
from app.models.support_access import SupportAccessGrant, SupportSession
from app.models.tenancy import Tenant
from app.schemas.support_access import AdminAccessStatus, AdminSessionPage, AdminSessionRow
from app.services import support_access as company_side
from app.services.audit import record_event
from app.services.platform.audit import record
from app.services.platform.tenants import get_tenant

CLOSED = frozenset({TenantStatus.SUSPENDED, TenantStatus.CANCELLED})


def _live(db: Session, tenant_id: int, now: datetime) -> SupportAccessGrant | None:
    return db.execute(
        select(SupportAccessGrant)
        .where(
            SupportAccessGrant.tenant_id == tenant_id,
            SupportAccessGrant.revoked_at.is_(None),
            SupportAccessGrant.starts_at <= now,
            SupportAccessGrant.ends_at > now,
        )
        .order_by(SupportAccessGrant.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _open_sessions(db: Session, tenant_id: int, now: datetime) -> int:
    return db.execute(
        select(func.count())
        .select_from(SupportSession)
        .where(
            SupportSession.tenant_id == tenant_id,
            SupportSession.ended_at.is_(None),
            SupportSession.expires_at > now,
        )
    ).scalar_one()


def access_status(db: Session, tenant_id: int) -> AdminAccessStatus:
    """Whether the owner has granted access now, until when, and how many sessions are open."""
    tenant = get_tenant(db, tenant_id)
    now = now_utc()
    grant = _live(db, tenant.id, now)
    open_sessions = _open_sessions(db, tenant.id, now)
    if grant is None:
        return AdminAccessStatus(
            live=False,
            grant_id=None,
            starts_at=None,
            ends_at=None,
            seconds_left=0,
            owner_only_figures=False,
            reason=None,
            ticket_number=None,
            granted_by_name=None,
            open_sessions=open_sessions,
        )
    owner = db.get(AppUser, grant.granted_by_user_id)
    ticket = db.get(SupportTicket, grant.ticket_id) if grant.ticket_id else None
    return AdminAccessStatus(
        live=True,
        grant_id=grant.id,
        starts_at=grant.starts_at,
        ends_at=grant.ends_at,
        seconds_left=rules.seconds_left(grant.ends_at, now),
        owner_only_figures=grant.include_costs,
        reason=grant.reason,
        ticket_number=ticket.number if ticket else None,
        granted_by_name=owner.full_name if owner else None,
        open_sessions=open_sessions,
    )


def enter(
    db: Session, tenant_id: int, admin_id: int, reason: str
) -> tuple[SupportSession, str, Tenant]:
    """Open a support session and mint its token. 409 NO_SUPPORT_GRANT without a live grant;
    409 TENANT_NOT_OPEN for a suspended or cancelled company. The admin's earlier open session
    at this company, if any, ends (replaced)."""
    tenant = get_tenant(db, tenant_id)
    if tenant.status in CLOSED:
        raise BusinessRuleError(
            "This company is suspended or cancelled, so nobody can enter it.",
            code="TENANT_NOT_OPEN",
        )
    now = now_utc()
    with tenant_context(db, tenant.id):
        grant = _live(db, tenant.id, now)
        if grant is None:
            raise BusinessRuleError(
                "The company's owner has not granted Duolink support access, or it has ended. "
                "Ask the owner to turn it on in Settings, Duolink support access.",
                code="NO_SUPPORT_GRANT",
            )
        earlier = db.execute(
            select(SupportSession).where(
                SupportSession.tenant_id == tenant.id,
                SupportSession.admin_id == admin_id,
                SupportSession.ended_at.is_(None),
            )
        ).scalars()
        for old in earlier:
            company_side.end_session(db, old, SupportSessionEnd.REPLACED, now, user_id=None)
        session = SupportSession(
            tenant_id=tenant.id,
            grant_id=grant.id,
            admin_id=admin_id,
            reason=reason.strip(),
            started_at=now,
            expires_at=rules.token_expiry(now, grant.ends_at),
            request_count=0,
        )
        db.add(session)
        db.flush()
        details = {
            "session_id": session.id,
            "grant_id": grant.id,
            "reason": session.reason,
            "expires_at": session.expires_at,
            "owner_only_figures": grant.include_costs,
        }
        record_event(
            db,
            AuditAction.SUPPORT_ENTER,
            "support_session",
            session.id,
            {**details, "admin_id": admin_id},
        )
        record(
            db, PlatformAction.SUPPORT_SESSION_START, admin_id, tenant_id=tenant.id, details=details
        )
        db.commit()
    token = create_support_token(
        SupportClaims(
            admin_id=admin_id, tenant_id=tenant.id, grant_id=grant.id, session_id=session.id
        ),
        session.expires_at,
        now,
    )
    return session, token, tenant


def list_sessions(
    db: Session,
    *,
    tenant_id: int | None = None,
    admin_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> AdminSessionPage:
    """Every support session at every company, newest first: the Audit "Company access" tab."""
    now = now_utc()
    filters = []
    if tenant_id is not None:
        filters.append(SupportSession.tenant_id == tenant_id)
    if admin_id is not None:
        filters.append(SupportSession.admin_id == admin_id)
    total = db.execute(
        select(func.count()).select_from(SupportSession).where(*filters)
    ).scalar_one()
    unended = SupportSession.ended_at.is_(None)
    open_count = db.execute(
        select(func.count())
        .select_from(SupportSession)
        .where(*filters, unended, SupportSession.expires_at > now)
    ).scalar_one()
    stale = db.execute(
        select(func.count())
        .select_from(SupportSession)
        .where(*filters, unended, SupportSession.expires_at <= now)
    ).scalar_one()
    rows = db.execute(
        select(
            SupportSession,
            Tenant.slug,
            Tenant.name,
            PlatformAdmin.full_name,
            SupportAccessGrant.include_costs,
        )
        .join(Tenant, Tenant.id == SupportSession.tenant_id)
        .join(PlatformAdmin, PlatformAdmin.id == SupportSession.admin_id)
        .join(SupportAccessGrant, SupportAccessGrant.id == SupportSession.grant_id)
        .where(*filters)
        .order_by(SupportSession.started_at.desc(), SupportSession.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    items = [
        AdminSessionRow(
            id=s.id,
            tenant_id=s.tenant_id,
            tenant_slug=slug,
            tenant_name=name,
            admin_id=s.admin_id,
            admin_name=admin_name,
            reason=s.reason,
            status=company_side.session_status(s, now),
            started_at=s.started_at,
            expires_at=s.expires_at,
            ended_at=rules.effective_end(s.ended_at, s.expires_at, now),
            end_reason=s.end_reason,
            request_count=s.request_count,
            owner_only_figures=include_costs,
        )
        for s, slug, name, admin_name, include_costs in rows
    ]
    return AdminSessionPage(
        items=items, total=total, open=open_count, stale=stale, limit=limit, offset=offset
    )
