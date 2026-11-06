"""Help: a company raises questions to Duolink and reads the answers (Milestone 22).

Owner and accountant see every ticket of the company; counter staff only their own. These
routes work while the company is read-only (see `services/subscription_access.py`). Nothing here
carries an amount.
"""

from fastapi import APIRouter, status

from app.api.deps import CurrentPrincipal, DbSession, Principal
from app.models.enums import Role, SupportStatus
from app.schemas.common import Page
from app.schemas.support import TicketCreate, TicketDetail, TicketReply, TicketRow, UnreadCount
from app.services import support as service
from app.services.support import Viewer

router = APIRouter(prefix="/support", tags=["support"])


def _viewer(principal: Principal) -> Viewer:
    return Viewer(
        user_id=principal.user_id,
        is_counter=principal.role is Role.COUNTER,
        marks_seen=not principal.is_support,
    )


@router.get("/tickets", response_model=Page[TicketRow])
def list_tickets(
    principal: CurrentPrincipal, db: DbSession, status: SupportStatus | None = None
) -> Page[TicketRow]:
    """The company's tickets, newest activity first (a counter user: only their own)."""
    rows, total = service.list_tickets(db, _viewer(principal), status)
    return Page[TicketRow](items=rows, total=total, limit=total, offset=0)


@router.get("/tickets/unread-count", response_model=UnreadCount)
def unread_count(principal: CurrentPrincipal, db: DbSession) -> UnreadCount:
    """Tickets with an answer from Duolink not yet opened. The Help menu polls this."""
    return service.unread_count(db, _viewer(principal))


@router.post("/tickets", response_model=TicketDetail, status_code=status.HTTP_201_CREATED)
def create_ticket(body: TicketCreate, principal: CurrentPrincipal, db: DbSession) -> TicketDetail:
    return service.create(db, _viewer(principal), body)


@router.get("/tickets/{ticket_id}", response_model=TicketDetail)
def get_ticket(ticket_id: int, principal: CurrentPrincipal, db: DbSession) -> TicketDetail:
    """404 TICKET_NOT_FOUND for a missing ticket and for another counter user's. Opening it marks
    Duolink's answers as read."""
    return service.get(db, _viewer(principal), ticket_id)


@router.post("/tickets/{ticket_id}/reply", response_model=TicketDetail)
def reply(
    ticket_id: int, body: TicketReply, principal: CurrentPrincipal, db: DbSession
) -> TicketDetail:
    """409 TICKET_CLOSED. A reply to a resolved ticket, or one waiting on the company, reopens
    it."""
    return service.reply(db, _viewer(principal), ticket_id, body)


@router.post("/tickets/{ticket_id}/close", response_model=TicketDetail)
def close(ticket_id: int, principal: CurrentPrincipal, db: DbSession) -> TicketDetail:
    """Only the person who raised the ticket: 403 TICKET_NOT_YOURS. 409 TICKET_CLOSED."""
    return service.close(db, _viewer(principal), ticket_id)
