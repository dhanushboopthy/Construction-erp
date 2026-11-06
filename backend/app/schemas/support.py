"""Support tickets (Milestone 22). The company writes to Duolink, so Duolink's admin may read the
subject and the messages. There is no amount in any of these shapes (ADR 0013)."""

from datetime import datetime

from pydantic import Field, model_validator

from app.models.enums import (
    AuthorKind,
    SupportCategory,
    SupportPriority,
    SupportStatus,
)
from app.schemas.common import Schema


class TicketCreate(Schema):
    subject: str = Field(min_length=3, max_length=200)
    category: SupportCategory
    priority: SupportPriority = SupportPriority.NORMAL
    body: str = Field(min_length=1, max_length=5000)


class TicketReply(Schema):
    body: str = Field(min_length=1, max_length=5000)


class MessageOut(Schema):
    id: int
    author_kind: AuthorKind
    author_name: str
    body: str
    created_at: datetime


class TicketRow(Schema):
    id: int
    number: str
    subject: str
    category: SupportCategory
    priority: SupportPriority
    status: SupportStatus
    raised_by_name: str
    created_at: datetime
    last_reply_at: datetime
    unread: bool


class TicketDetail(TicketRow):
    assigned_admin_name: str | None
    closed_at: datetime | None
    can_close: bool  # the signed-in user raised it and it is not closed
    messages: list[MessageOut]


class UnreadCount(Schema):
    unread: int


# ---------------------------------------------------------------- Duolink's side


class AdminTicketRow(TicketRow):
    tenant_id: int
    tenant_name: str
    tenant_slug: str
    assigned_admin_id: int | None
    assigned_admin_name: str | None


class AdminTicketDetail(AdminTicketRow):
    closed_at: datetime | None
    messages: list[MessageOut]


class AdminReply(Schema):
    """At least one of the two is needed."""

    body: str | None = Field(default=None, max_length=5000)
    status: SupportStatus | None = None

    @model_validator(mode="after")
    def _something_to_say(self) -> "AdminReply":
        if not (self.body and self.body.strip()) and self.status is None:
            raise ValueError("Write a message, choose a status, or both.")
        return self


class AdminTicketUpdate(Schema):
    status: SupportStatus | None = None
    priority: SupportPriority | None = None
    assigned_admin_id: int | None = None  # sent as null: unassign


class TicketCounts(Schema):
    open: int
    in_progress: int
    waiting_on_company: int
    resolved: int
    closed: int
    urgent_open: int  # urgent and not resolved or closed
    unassigned: int  # not resolved or closed, and nobody assigned


class AdminTicketPage(Schema):
    items: list[AdminTicketRow]
    total: int
    limit: int
    offset: int
    counts: TicketCounts
