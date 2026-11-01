"""Support tickets: numbers, who may see and close one, and how a reply moves its status
(Milestone 22)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.support import (
    CATEGORIES,
    PRIORITIES,
    STATUSES,
    SupportRuleError,
    after_admin_reply,
    after_company_reply,
    can_see,
    check_close,
    format_ticket_number,
    has_unread,
)

T0 = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)


def test_the_vocabularies():
    assert CATEGORIES == ("sign_in", "billing", "gst_eway", "stock", "printing", "other")
    assert PRIORITIES == ("low", "normal", "high", "urgent")
    assert STATUSES == ("open", "in_progress", "waiting_on_company", "resolved", "closed")


def test_ticket_numbers_are_padded():
    assert format_ticket_number(1) == "T-000001"
    assert format_ticket_number(12) == "T-000012"
    assert format_ticket_number(1234567) == "T-1234567"  # never cut off


def test_counter_users_see_only_their_own_tickets():
    assert can_see(is_counter=True, raised_by=7, user_id=7)
    assert not can_see(is_counter=True, raised_by=7, user_id=8)
    assert can_see(is_counter=False, raised_by=7, user_id=8)  # owner and accountant see all


def test_only_the_person_who_raised_a_ticket_closes_it():
    check_close(status="open", raised_by=7, user_id=7)
    check_close(status="resolved", raised_by=7, user_id=7)
    with pytest.raises(SupportRuleError) as other:
        check_close(status="open", raised_by=7, user_id=8)
    assert other.value.code == "TICKET_NOT_YOURS"
    with pytest.raises(SupportRuleError) as closed:
        check_close(status="closed", raised_by=7, user_id=7)
    assert closed.value.code == "TICKET_CLOSED"


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("open", "open"),
        ("in_progress", "in_progress"),
        ("waiting_on_company", "open"),  # they answered: Duolink's turn
        ("resolved", "open"),  # not resolved after all
    ],
)
def test_a_company_reply_returns_the_ticket_to_duolink(before, after):
    assert after_company_reply(before) == after


def test_a_closed_ticket_takes_no_company_reply():
    with pytest.raises(SupportRuleError) as err:
        after_company_reply("closed")
    assert err.value.code == "TICKET_CLOSED"


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("open", "waiting_on_company"),
        ("in_progress", "waiting_on_company"),
        ("waiting_on_company", "waiting_on_company"),
        ("resolved", "resolved"),
    ],
)
def test_an_admin_reply_without_a_status_waits_for_the_company(before, after):
    assert after_admin_reply(before, requested=None, has_body=True) == after


def test_an_admin_can_set_the_status_with_or_without_a_message():
    assert after_admin_reply("open", requested="resolved", has_body=True) == "resolved"
    assert after_admin_reply("open", requested="in_progress", has_body=False) == "in_progress"
    assert after_admin_reply("closed", requested="open", has_body=True) == "open"  # reopen


def test_an_admin_reply_needs_a_body_or_a_status():
    with pytest.raises(SupportRuleError) as err:
        after_admin_reply("open", requested=None, has_body=False)
    assert err.value.code == "REPLY_EMPTY"


def test_a_message_on_a_closed_ticket_needs_it_reopened():
    with pytest.raises(SupportRuleError) as err:
        after_admin_reply("closed", requested=None, has_body=True)
    assert err.value.code == "TICKET_CLOSED"


def test_an_unknown_status_is_refused():
    with pytest.raises(SupportRuleError) as err:
        after_admin_reply("open", requested="done", has_body=True)
    assert err.value.code == "STATUS_UNKNOWN"


def test_unread_means_a_message_newer_than_the_last_time_it_was_opened():
    assert not has_unread(latest_message_at=None, seen_at=None)
    assert has_unread(latest_message_at=T0, seen_at=None)
    assert has_unread(latest_message_at=T0, seen_at=T0 - timedelta(minutes=1))
    assert not has_unread(latest_message_at=T0, seen_at=T0)
    assert not has_unread(latest_message_at=T0, seen_at=T0 + timedelta(minutes=1))
