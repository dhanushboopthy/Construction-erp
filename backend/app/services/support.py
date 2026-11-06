"""Support tickets, as the company sees them (Milestone 22): raise, list, read, reply and close.

An owner or accountant sees every ticket of the company; a counter user only their own. Every
query filters on the session's company. It works while the company is read-only (the exception
list in `subscription_access.py`). Duolink's side is `services/platform/support.py`.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFoundError, PermissionDeniedError
from app.core.tenancy import current_tenant_id
from app.domain import support as rules
from app.models.enums import (
    AuthorKind,
    SupportPriority,
    SupportStatus,
)
from app.models.platform import PlatformAdmin
from app.models.setup import AppUser
from app.models.support import SupportMessage, SupportTicket
from app.schemas.support import (
    MessageOut,
    TicketCreate,
    TicketDetail,
    TicketReply,
    TicketRow,
    UnreadCount,
)
from app.services.numbering import allocate_company_number

COUNTER_NAME = "support_ticket"
DUOLINK_NAME = "Duolink Support"  # the company never sees which admin answered


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Viewer:
    """The signed-in company user, as far as tickets care: who they are, and whether they are
    counter staff (who see only their own tickets)."""

    user_id: int
    is_counter: bool
    # False inside a read-only Duolink support session (M23): Duolink reading a ticket from
    # inside the company does not mark its answers as read by the company.
    marks_seen: bool = True


def _refuse(exc: rules.SupportRuleError) -> BusinessRuleError | PermissionDeniedError:
    if exc.code == "TICKET_NOT_YOURS":
        return PermissionDeniedError(str(exc), code=exc.code)
    return BusinessRuleError(str(exc), code=exc.code)


def latest_message_times(
    db: Session, ticket_ids: list[int], kind: AuthorKind
) -> dict[int, datetime]:
    """When the newest message by `kind` was written, per ticket."""
    if not ticket_ids:
        return {}
    rows = db.execute(
        select(SupportMessage.ticket_id, func.max(SupportMessage.created_at))
        .where(SupportMessage.ticket_id.in_(ticket_ids), SupportMessage.author_kind == kind)
        .group_by(SupportMessage.ticket_id)
    )
    return {row[0]: row[1] for row in rows}


def user_names(db: Session, user_ids: set[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    rows = db.execute(select(AppUser.id, AppUser.full_name).where(AppUser.id.in_(user_ids)))
    return {row[0]: row[1] for row in rows}


def admin_names(db: Session, admin_ids: set[int]) -> dict[int, str]:
    if not admin_ids:
        return {}
    rows = db.execute(
        select(PlatformAdmin.id, PlatformAdmin.full_name).where(PlatformAdmin.id.in_(admin_ids))
    )
    return {row[0]: row[1] for row in rows}


def messages_of(db: Session, ticket: SupportTicket, *, show_admin_names: bool) -> list[MessageOut]:
    rows = list(
        db.execute(
            select(SupportMessage)
            .where(SupportMessage.ticket_id == ticket.id)
            .order_by(SupportMessage.created_at, SupportMessage.id)
        ).scalars()
    )
    users = user_names(db, {m.author_user_id for m in rows if m.author_user_id})
    admins = (
        admin_names(db, {m.author_admin_id for m in rows if m.author_admin_id})
        if show_admin_names
        else {}
    )
    return [
        MessageOut(
            id=m.id,
            author_kind=m.author_kind,
            author_name=(
                users.get(m.author_user_id or 0, "Unknown")
                if m.author_kind is AuthorKind.COMPANY_USER
                else admins.get(m.author_admin_id or 0, DUOLINK_NAME)
            ),
            body=m.body,
            created_at=m.created_at,
        )
        for m in rows
    ]


def add_message(
    db: Session,
    ticket: SupportTicket,
    body: str,
    *,
    kind: AuthorKind,
    user_id: int | None = None,
    admin_id: int | None = None,
    now: datetime,
) -> None:
    db.add(
        SupportMessage(
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            body=body,
            author_kind=kind,
            author_user_id=user_id,
            author_admin_id=admin_id,
            created_at=now,
        )
    )
    ticket.last_reply_at = now


def set_status(ticket: SupportTicket, status: str, now: datetime) -> None:
    ticket.status = SupportStatus(status)
    ticket.closed_at = now if status == "closed" else None


# ---------------------------------------------------------------- the company's side


def _visible(db: Session, viewer: Viewer) -> list[ColumnElement[bool]]:
    conditions = [SupportTicket.tenant_id == current_tenant_id(db)]
    if viewer.is_counter:
        conditions.append(SupportTicket.raised_by_user_id == viewer.user_id)
    return conditions


def _load(db: Session, viewer: Viewer, ticket_id: int) -> SupportTicket:
    ticket = db.execute(
        select(SupportTicket).where(SupportTicket.id == ticket_id, *_visible(db, viewer))
    ).scalar_one_or_none()
    if ticket is None:  # another counter user's ticket looks the same as a missing one
        raise NotFoundError("Ticket not found", code="TICKET_NOT_FOUND")
    return ticket


def _rows(db: Session, tickets: list[SupportTicket]) -> list[TicketRow]:
    ids = [t.id for t in tickets]
    answered = latest_message_times(db, ids, AuthorKind.PLATFORM_ADMIN)
    names = user_names(db, {t.raised_by_user_id for t in tickets})
    return [
        TicketRow(
            id=t.id,
            number=t.number,
            subject=t.subject,
            category=t.category,
            priority=t.priority,
            status=t.status,
            raised_by_name=names.get(t.raised_by_user_id, "Unknown"),
            created_at=t.created_at,
            last_reply_at=t.last_reply_at,
            unread=rules.has_unread(
                latest_message_at=answered.get(t.id), seen_at=t.company_seen_at
            ),
        )
        for t in tickets
    ]


def _detail(db: Session, viewer: Viewer, ticket: SupportTicket) -> TicketDetail:
    row = _rows(db, [ticket])[0]
    assigned = (
        admin_names(db, {ticket.assigned_admin_id}).get(ticket.assigned_admin_id)
        if ticket.assigned_admin_id
        else None
    )
    return TicketDetail(
        **row.model_dump(),
        assigned_admin_name=DUOLINK_NAME if assigned else None,
        closed_at=ticket.closed_at,
        can_close=ticket.raised_by_user_id == viewer.user_id
        and ticket.status is not SupportStatus.CLOSED,
        messages=messages_of(db, ticket, show_admin_names=False),
    )


def list_tickets(
    db: Session, viewer: Viewer, status: SupportStatus | None
) -> tuple[list[TicketRow], int]:
    stmt = select(SupportTicket).where(*_visible(db, viewer))
    if status:
        stmt = stmt.where(SupportTicket.status == status)
    tickets = list(
        db.execute(stmt.order_by(SupportTicket.last_reply_at.desc(), SupportTicket.id.desc()))
        .scalars()
        .all()
    )
    return _rows(db, tickets), len(tickets)


def unread_count(db: Session, viewer: Viewer) -> UnreadCount:
    tickets = list(db.execute(select(SupportTicket).where(*_visible(db, viewer))).scalars())
    return UnreadCount(unread=sum(row.unread for row in _rows(db, tickets)))


def create(db: Session, viewer: Viewer, data: TicketCreate) -> TicketDetail:
    now = _now()
    number = rules.format_ticket_number(allocate_company_number(db, COUNTER_NAME))
    ticket = SupportTicket(
        tenant_id=current_tenant_id(db),
        number=number,
        subject=data.subject.strip(),
        category=data.category,
        priority=SupportPriority(data.priority),
        status=SupportStatus.OPEN,
        raised_by_user_id=viewer.user_id,
        last_reply_at=now,
        company_seen_at=now,
    )
    db.add(ticket)
    db.flush()
    add_message(
        db,
        ticket,
        data.body.strip(),
        kind=AuthorKind.COMPANY_USER,
        user_id=viewer.user_id,
        now=now,
    )
    db.commit()
    return _detail(db, viewer, ticket)


def get(db: Session, viewer: Viewer, ticket_id: int) -> TicketDetail:
    """Opening a ticket marks Duolink's replies as read."""
    ticket = _load(db, viewer, ticket_id)
    if viewer.marks_seen:
        ticket.company_seen_at = _now()
        db.commit()
    return _detail(db, viewer, ticket)


def reply(db: Session, viewer: Viewer, ticket_id: int, data: TicketReply) -> TicketDetail:
    ticket = _load(db, viewer, ticket_id)
    try:
        status = rules.after_company_reply(ticket.status.value)
    except rules.SupportRuleError as exc:
        raise _refuse(exc) from exc
    now = _now()
    add_message(
        db,
        ticket,
        data.body.strip(),
        kind=AuthorKind.COMPANY_USER,
        user_id=viewer.user_id,
        now=now,
    )
    set_status(ticket, status, now)
    ticket.company_seen_at = now
    db.commit()
    return _detail(db, viewer, ticket)


def close(db: Session, viewer: Viewer, ticket_id: int) -> TicketDetail:
    ticket = _load(db, viewer, ticket_id)
    try:
        rules.check_close(
            status=ticket.status.value,
            raised_by=ticket.raised_by_user_id,
            user_id=viewer.user_id,
        )
    except rules.SupportRuleError as exc:
        raise _refuse(exc) from exc
    set_status(ticket, "closed", _now())
    db.commit()
    return _detail(db, viewer, ticket)
