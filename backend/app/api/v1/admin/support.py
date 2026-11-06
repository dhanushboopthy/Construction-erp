"""Duolink answers the companies' support tickets (Milestone 22). Support admins may do all of
this: it is their job. The company wrote these messages to Duolink, so the subject and the
messages are readable here (ADR 0013); there is no amount in any answer."""

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.api.deps import DbSession, PlatformAdminUser
from app.models.enums import SupportPriority, SupportStatus
from app.schemas.support import (
    AdminReply,
    AdminTicketDetail,
    AdminTicketPage,
    AdminTicketUpdate,
)
from app.services.platform import support as service

router = APIRouter(prefix="/support", tags=["admin"])


@router.get("/tickets", response_model=AdminTicketPage)
def list_tickets(
    admin: PlatformAdminUser,
    db: DbSession,
    status: SupportStatus | None = None,
    priority: SupportPriority | None = None,
    tenant_id: int | None = None,
    assigned: Literal["me", "unassigned"] | None = None,
    q: Annotated[str | None, Query(description="subject, ticket number or company")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminTicketPage:
    """Newest activity first. `counts` are for every filter except `status`."""
    return service.list_tickets(
        db,
        admin.admin_id,
        status=status,
        priority=priority,
        tenant_id=tenant_id,
        assigned=assigned,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.get("/tickets/{ticket_id}", response_model=AdminTicketDetail)
def get_ticket(ticket_id: int, _: PlatformAdminUser, db: DbSession) -> AdminTicketDetail:
    """Opening it marks the company's messages as read by Duolink."""
    return service.get(db, ticket_id)


@router.post("/tickets/{ticket_id}/reply", response_model=AdminTicketDetail)
def reply(
    ticket_id: int, body: AdminReply, admin: PlatformAdminUser, db: DbSession
) -> AdminTicketDetail:
    """A message, a new status, or both; neither is 422. A message with no status
    moves an open or in-progress ticket to waiting on the company. 409 TICKET_CLOSED for a
    message on a closed ticket (send a status to reopen it)."""
    return service.reply(db, ticket_id, body, admin.admin_id)


@router.patch("/tickets/{ticket_id}", response_model=AdminTicketDetail)
def update_ticket(
    ticket_id: int, body: AdminTicketUpdate, admin: PlatformAdminUser, db: DbSession
) -> AdminTicketDetail:
    """Change the status, the priority or the assignee (`assigned_admin_id: null` unassigns)."""
    return service.update(db, ticket_id, body, admin.admin_id)
