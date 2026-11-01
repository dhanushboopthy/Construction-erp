"""Support tickets between a company and Duolink (Milestone 22, ADR 0013).

Pure rules: ticket numbers, who may see and close a ticket, how a reply moves the status, and
what counts as unread. A ticket is a conversation: a company user writes, Duolink answers.
"""

from datetime import datetime

CATEGORIES = ("sign_in", "billing", "gst_eway", "stock", "printing", "other")
PRIORITIES = ("low", "normal", "high", "urgent")
STATUSES = ("open", "in_progress", "waiting_on_company", "resolved", "closed")


class SupportRuleError(ValueError):
    """The support rules refuse this. `code` is the API error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def format_ticket_number(sequence: int) -> str:
    return f"T-{sequence:06d}"


def can_see(*, is_counter: bool, raised_by: int, user_id: int) -> bool:
    """An owner or accountant sees every ticket of the company; a counter user their own."""
    return not is_counter or raised_by == user_id


def check_close(*, status: str, raised_by: int, user_id: int) -> None:
    if raised_by != user_id:
        raise SupportRuleError(
            "TICKET_NOT_YOURS", "Only the person who raised a ticket can close it."
        )
    if status == "closed":
        raise SupportRuleError("TICKET_CLOSED", "This ticket is closed.")


def after_company_reply(status: str) -> str:
    """The company answered: Duolink's turn again. A resolved ticket reopens."""
    if status == "closed":
        raise SupportRuleError("TICKET_CLOSED", "This ticket is closed. Raise a new one.")
    return "open" if status in {"waiting_on_company", "resolved"} else status


def after_admin_reply(status: str, *, requested: str | None, has_body: bool) -> str:
    """Duolink replied, changed the status, or both. A message with no status named hands the
    ticket to the company (an open or in-progress one becomes waiting on the company)."""
    if requested is not None and requested not in STATUSES:
        raise SupportRuleError("STATUS_UNKNOWN", f"Not a status: {requested}.")
    if requested is None and not has_body:
        raise SupportRuleError("REPLY_EMPTY", "Write a message, choose a status, or both.")
    if requested is not None:
        return requested
    if status == "closed":
        raise SupportRuleError("TICKET_CLOSED", "This ticket is closed. Reopen it to reply.")
    return "waiting_on_company" if status in {"open", "in_progress"} else status


def has_unread(*, latest_message_at: datetime | None, seen_at: datetime | None) -> bool:
    """A message arrived that the reader has not yet opened the ticket to see."""
    if latest_message_at is None:
        return False
    return seen_at is None or seen_at < latest_message_at
