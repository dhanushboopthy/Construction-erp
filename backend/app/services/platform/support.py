"""Support tickets, as Duolink sees them (Milestone 22): every company's tickets, replies, and
changes of status, priority or assignee. The company wrote these to Duolink, so the admin may
read subjects and messages (ADR 0013); no amount is in any of it. Every reply and change is
written to the platform audit log, without the message text."""

from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFoundError
from app.domain import support as rules
from app.models.enums import (
    AuthorKind,
    PlatformAction,
    SupportPriority,
    SupportStatus,
)
from app.models.platform import PlatformAdmin
from app.models.support import SupportTicket
from app.models.tenancy import Tenant
from app.schemas.support import (
    AdminReply,
    AdminTicketDetail,
    AdminTicketPage,
    AdminTicketRow,
    AdminTicketUpdate,
    TicketCounts,
)
from app.services.platform.audit import record
from app.services.support import (
    add_message,
    admin_names,
    latest_message_times,
    messages_of,
    set_status,
    user_names,
)

OPEN_STATES = (SupportStatus.OPEN, SupportStatus.IN_PROGRESS, SupportStatus.WAITING_ON_COMPANY)


def _now() -> datetime:
    return datetime.now(UTC)


def _refuse(exc: rules.SupportRuleError) -> BusinessRuleError:
    return BusinessRuleError(str(exc), code=exc.code)


def _rows(db: Session, pairs: list[tuple[SupportTicket, Tenant]]) -> list[AdminTicketRow]:
    ids = [t.id for t, _ in pairs]
    asked = latest_message_times(db, ids, AuthorKind.COMPANY_USER)
    raised = user_names(db, {t.raised_by_user_id for t, _ in pairs})
    assigned = admin_names(db, {t.assigned_admin_id for t, _ in pairs if t.assigned_admin_id})
    return [
        AdminTicketRow(
            id=t.id,
            number=t.number,
            subject=t.subject,
            category=t.category,
            priority=t.priority,
            status=t.status,
            raised_by_name=raised.get(t.raised_by_user_id, "Unknown"),
            created_at=t.created_at,
            last_reply_at=t.last_reply_at,
            unread=rules.has_unread(latest_message_at=asked.get(t.id), seen_at=t.admin_seen_at),
            tenant_id=tenant.id,
            tenant_name=tenant.name,
            tenant_slug=tenant.slug,
            assigned_admin_id=t.assigned_admin_id,
            assigned_admin_name=assigned.get(t.assigned_admin_id or 0),
        )
        for t, tenant in pairs
    ]


def _counts(db: Session, filters: list[ColumnElement[bool]]) -> TicketCounts:
    by_status = dict(
        db.execute(
            select(SupportTicket.status, func.count())
            .where(*filters)
            .group_by(SupportTicket.status)
        ).all()
    )
    live = SupportTicket.status.in_(OPEN_STATES)
    urgent = db.execute(
        select(func.count()).where(*filters, live, SupportTicket.priority == SupportPriority.URGENT)
    ).scalar_one()
    unassigned = db.execute(
        select(func.count()).where(*filters, live, SupportTicket.assigned_admin_id.is_(None))
    ).scalar_one()
    return TicketCounts(
        open=by_status.get(SupportStatus.OPEN, 0),
        in_progress=by_status.get(SupportStatus.IN_PROGRESS, 0),
        waiting_on_company=by_status.get(SupportStatus.WAITING_ON_COMPANY, 0),
        resolved=by_status.get(SupportStatus.RESOLVED, 0),
        closed=by_status.get(SupportStatus.CLOSED, 0),
        urgent_open=urgent,
        unassigned=unassigned,
    )


def list_tickets(
    db: Session,
    admin_id: int,
    *,
    status: SupportStatus | None,
    priority: SupportPriority | None,
    tenant_id: int | None,
    assigned: Literal["me", "unassigned"] | None,
    q: str | None,
    limit: int,
    offset: int,
) -> AdminTicketPage:
    filters: list[ColumnElement[bool]] = []
    if priority:
        filters.append(SupportTicket.priority == priority)
    if tenant_id is not None:
        filters.append(SupportTicket.tenant_id == tenant_id)
    if assigned == "me":
        filters.append(SupportTicket.assigned_admin_id == admin_id)
    elif assigned == "unassigned":
        filters.append(SupportTicket.assigned_admin_id.is_(None))
    if q and q.strip():
        like = f"%{q.strip()}%"
        filters.append(
            or_(
                SupportTicket.subject.ilike(like),
                SupportTicket.number.ilike(like),
                SupportTicket.tenant_id.in_(
                    select(Tenant.id).where(or_(Tenant.name.ilike(like), Tenant.slug.ilike(like)))
                ),
            )
        )
    counts = _counts(db, filters)  # counts by status ignore the status filter itself
    if status:
        filters.append(SupportTicket.status == status)
    total = db.execute(select(func.count()).select_from(SupportTicket).where(*filters)).scalar_one()
    pairs = [
        (row[0], row[1])
        for row in db.execute(
            select(SupportTicket, Tenant)
            .join(Tenant, Tenant.id == SupportTicket.tenant_id)
            .where(*filters)
            .order_by(SupportTicket.last_reply_at.desc(), SupportTicket.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    ]
    return AdminTicketPage(
        items=_rows(db, pairs), total=total, limit=limit, offset=offset, counts=counts
    )


def _load(db: Session, ticket_id: int) -> tuple[SupportTicket, Tenant]:
    row = db.execute(
        select(SupportTicket, Tenant)
        .join(Tenant, Tenant.id == SupportTicket.tenant_id)
        .where(SupportTicket.id == ticket_id)
    ).first()
    if row is None:
        raise NotFoundError("Ticket not found", code="TICKET_NOT_FOUND")
    return row[0], row[1]


def _detail(db: Session, ticket: SupportTicket, tenant: Tenant) -> AdminTicketDetail:
    row = _rows(db, [(ticket, tenant)])[0]
    return AdminTicketDetail(
        **row.model_dump(),
        closed_at=ticket.closed_at,
        messages=messages_of(db, ticket, show_admin_names=True),
    )


def get(db: Session, ticket_id: int) -> AdminTicketDetail:
    """Opening a ticket marks the company's messages as read by Duolink."""
    ticket, tenant = _load(db, ticket_id)
    ticket.admin_seen_at = _now()
    db.commit()
    return _detail(db, ticket, tenant)


def reply(db: Session, ticket_id: int, data: AdminReply, admin_id: int) -> AdminTicketDetail:
    ticket, tenant = _load(db, ticket_id)
    body = (data.body or "").strip()
    was = ticket.status.value
    try:
        status = rules.after_admin_reply(
            was, requested=data.status.value if data.status else None, has_body=bool(body)
        )
    except rules.SupportRuleError as exc:
        raise _refuse(exc) from exc
    now = _now()
    if body:
        add_message(db, ticket, body, kind=AuthorKind.PLATFORM_ADMIN, admin_id=admin_id, now=now)
    if status != was:
        set_status(ticket, status, now)
    ticket.admin_seen_at = now
    record(
        db,
        PlatformAction.SUPPORT_REPLY,
        admin_id,
        tenant_id=tenant.id,
        details={"ticket": ticket.number, "from": was, "to": status, "message": bool(body)},
    )
    db.commit()
    return _detail(db, ticket, tenant)


def update(
    db: Session, ticket_id: int, data: AdminTicketUpdate, admin_id: int
) -> AdminTicketDetail:
    ticket, tenant = _load(db, ticket_id)
    changes: dict[str, dict[str, str | int | None]] = {}
    now = _now()
    if data.status is not None and data.status != ticket.status:
        changes["status"] = {"from": ticket.status.value, "to": data.status.value}
        set_status(ticket, data.status.value, now)
    if data.priority is not None and data.priority != ticket.priority:
        changes["priority"] = {"from": ticket.priority.value, "to": data.priority.value}
        ticket.priority = data.priority
    if "assigned_admin_id" in data.model_fields_set and (
        data.assigned_admin_id != ticket.assigned_admin_id
    ):
        if data.assigned_admin_id is not None:
            assignee = db.get(PlatformAdmin, data.assigned_admin_id)
            if assignee is None or not assignee.is_active:
                raise NotFoundError("No active admin has that id", code="ADMIN_NOT_FOUND")
        changes["assigned_admin_id"] = {
            "from": ticket.assigned_admin_id,
            "to": data.assigned_admin_id,
        }
        ticket.assigned_admin_id = data.assigned_admin_id
    if changes:
        record(
            db,
            PlatformAction.SUPPORT_UPDATE,
            admin_id,
            tenant_id=tenant.id,
            details={"ticket": ticket.number, **changes},
        )
    db.commit()
    return _detail(db, ticket, tenant)
