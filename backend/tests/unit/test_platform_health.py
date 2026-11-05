"""System health, the notifications bell and maintenance mode (Milestone 24)."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.domain.platform_health import (
    BACKUP_STALE_HOURS,
    DISK_LOW_FREE_PERCENT,
    EXPIRING_DAYS,
    FAILED_ADMIN_SIGN_INS_LIMIT,
    MAINTENANCE_CACHE_SECONDS,
    MAINTENANCE_MESSAGE_MAX,
    RESTORE_MESSAGE,
    Disk,
    Level,
    PlatformRuleError,
    Signals,
    backup_is_stale,
    cache_is_fresh,
    changelog_version,
    clean_message,
    csv_cell,
    day_bounds,
    effective_maintenance,
    free_percent,
    hours_since,
    notifications,
    parse_last_success,
)

NOW = datetime(2026, 11, 3, 6, 0, tzinfo=UTC)
QUIET = Signals(
    expiring=0,
    expired=0,
    trials_ending=0,
    new_tickets=0,
    urgent_tickets=0,
    open_support_sessions=0,
    backups_watched=True,
    last_backup_at=NOW - timedelta(hours=3),
    disks=(Disk("backups", total_bytes=1000, free_bytes=500),),
    failed_admin_sign_ins=0,
)


def _ids(signals: Signals) -> list[str]:
    return [n.id for n in notifications(signals, NOW)]


def _one(signals: Signals):
    (item,) = notifications(signals, NOW)
    return item


def test_the_thresholds_are_the_ones_the_task_names():
    assert (BACKUP_STALE_HOURS, DISK_LOW_FREE_PERCENT, FAILED_ADMIN_SIGN_INS_LIMIT) == (26, 20, 10)
    assert (EXPIRING_DAYS, MAINTENANCE_CACHE_SECONDS) == (7, 5)


# ------------------------------------------------------------------ the bell


def test_a_quiet_platform_rings_no_bell():
    assert notifications(QUIET, NOW) == []


def test_subscriptions_expiring_within_seven_days_warn():
    item = _one(Signals(**{**QUIET.__dict__, "expiring": 2}))
    assert (item.id, item.level) == ("subscriptions-expiring", Level.WARNING)
    assert item.title == "2 subscriptions end within 7 days"
    assert item.link == "/admin/subscriptions?status=active&expiring_within=7"


def test_expired_companies_are_critical_and_singular_reads_right():
    item = _one(Signals(**{**QUIET.__dict__, "expired": 1}))
    assert (item.id, item.level) == ("companies-expired", Level.CRITICAL)
    assert item.title == "1 company has expired"
    assert "read-only" in item.body
    assert item.link == "/admin/subscriptions?status=expired"


def test_plural_expired_companies():
    assert _one(Signals(**{**QUIET.__dict__, "expired": 3})).title == "3 companies have expired"


def test_trials_ending_warn():
    item = _one(Signals(**{**QUIET.__dict__, "trials_ending": 1}))
    assert (item.id, item.level, item.title) == (
        "trials-ending",
        Level.WARNING,
        "1 trial ends within 7 days",
    )
    assert item.link == "/admin/subscriptions?status=trial&expiring_within=7"


def test_new_tickets_inform_and_urgent_ones_warn():
    items = notifications(Signals(**{**QUIET.__dict__, "new_tickets": 4, "urgent_tickets": 1}), NOW)
    assert [(n.id, n.level, n.title) for n in items] == [
        ("tickets-urgent", Level.WARNING, "1 urgent ticket is open"),
        ("tickets-new", Level.INFO, "4 new tickets are waiting"),
    ]
    assert items[0].link == "/admin/support?priority=urgent"
    assert items[1].link == "/admin/support?status=open"


def test_plural_urgent_and_single_new_ticket():
    items = notifications(Signals(**{**QUIET.__dict__, "new_tickets": 1, "urgent_tickets": 2}), NOW)
    assert [n.title for n in items] == ["2 urgent tickets are open", "1 new ticket is waiting"]


def test_support_sessions_left_open_warn():
    item = _one(Signals(**{**QUIET.__dict__, "open_support_sessions": 1}))
    assert (item.id, item.level) == ("support-sessions-open", Level.WARNING)
    assert item.title == "1 support session was left open"
    two = _one(Signals(**{**QUIET.__dict__, "open_support_sessions": 2}))
    assert two.title == "2 support sessions were left open"


def test_a_backup_older_than_26_hours_is_critical():
    old = Signals(**{**QUIET.__dict__, "last_backup_at": NOW - timedelta(hours=27)})
    item = _one(old)
    assert (item.id, item.level) == ("backup-stale", Level.CRITICAL)
    assert item.title == "The last backup is 27 hours old"
    assert item.link == "/admin/system"
    exactly = Signals(**{**QUIET.__dict__, "last_backup_at": NOW - timedelta(hours=26)})
    assert notifications(exactly, NOW) == []  # 26 hours is still on time


def test_no_backup_at_all_is_critical_when_backups_are_watched():
    item = _one(Signals(**{**QUIET.__dict__, "last_backup_at": None}))
    assert (item.id, item.title) == ("backup-stale", "No backup has been recorded")


def test_an_unwatched_backup_folder_rings_nothing():
    unwatched = Signals(**{**QUIET.__dict__, "backups_watched": False, "last_backup_at": None})
    assert notifications(unwatched, NOW) == []


def test_a_disk_below_20_percent_free_is_critical():
    low = Disk("files", total_bytes=1000, free_bytes=150)
    item = _one(Signals(**{**QUIET.__dict__, "disks": (low,)}))
    assert (item.id, item.level) == ("disk-low-files", Level.CRITICAL)
    assert item.title == "The files disk is 15.0% free"
    at_floor = Disk("files", total_bytes=1000, free_bytes=200)
    assert notifications(Signals(**{**QUIET.__dict__, "disks": (at_floor,)}), NOW) == []


def test_a_disk_of_unknown_size_rings_nothing():
    empty = Disk("files", total_bytes=0, free_bytes=0)
    assert notifications(Signals(**{**QUIET.__dict__, "disks": (empty,)}), NOW) == []


def test_more_than_ten_failed_admin_sign_ins_warn():
    at_limit = Signals(**{**QUIET.__dict__, "failed_admin_sign_ins": 10})
    assert notifications(at_limit, NOW) == []
    item = _one(Signals(**{**QUIET.__dict__, "failed_admin_sign_ins": 11}))
    assert (item.id, item.level) == ("admin-sign-ins-failed", Level.WARNING)
    assert item.title == "11 failed admin sign-ins in 24 hours"
    assert item.link == "/admin/audit?tab=admin&action=login_failed"


def test_critical_items_come_first_then_warnings_then_information():
    busy = Signals(
        **{
            **QUIET.__dict__,
            "new_tickets": 1,
            "expiring": 1,
            "expired": 1,
            "last_backup_at": None,
        }
    )
    assert _ids(busy) == [
        "companies-expired",
        "backup-stale",
        "subscriptions-expiring",
        "tickets-new",
    ]


# ------------------------------------------------------------------ health figures


def test_free_percent_has_one_decimal_and_no_float():
    assert free_percent(3, 1) == Decimal("33.3")
    assert free_percent(1000, 1000) == Decimal("100.0")
    assert free_percent(0, 0) is None


def test_hours_since_and_stale_backups():
    assert hours_since(NOW - timedelta(minutes=150), NOW) == 2
    assert hours_since(None, NOW) is None
    assert not backup_is_stale(NOW - timedelta(hours=BACKUP_STALE_HOURS), NOW)
    assert backup_is_stale(NOW - timedelta(hours=BACKUP_STALE_HOURS, seconds=1), NOW)
    assert backup_is_stale(None, NOW)


def test_the_last_success_marker_holds_epoch_seconds():
    assert parse_last_success("1793685600\n") == datetime(2026, 11, 3, 6, 0, tzinfo=UTC)
    assert parse_last_success("") is None
    assert parse_last_success("yesterday") is None
    assert parse_last_success("-5") is None


def test_the_version_is_the_newest_changelog_heading():
    text = "# Changelog\n\n## 1.17.0 (M24): health\n\n- x\n\n## 1.16.0 (M22): tickets\n"
    assert changelog_version(text) == "1.17.0"
    assert changelog_version("# Changelog\n\nNothing yet.\n") is None


def test_day_bounds_cover_whole_shop_days():
    start, end = day_bounds(date(2026, 11, 1), date(2026, 11, 2))
    assert start == datetime(2026, 10, 31, 18, 30, tzinfo=UTC)  # midnight in India
    assert end == datetime(2026, 11, 2, 18, 30, tzinfo=UTC)  # the end of 2 November
    assert day_bounds(None, None) == (None, None)
    only_to = day_bounds(None, date(2026, 11, 2))
    assert only_to == (None, datetime(2026, 11, 2, 18, 30, tzinfo=UTC))


def test_csv_cells_never_start_a_spreadsheet_formula():
    assert csv_cell("reason: Unpaid") == "reason: Unpaid"
    assert csv_cell("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    for lead in "+-@\t\r":
        assert csv_cell(f"{lead}x") == f"'{lead}x"
    assert csv_cell("") == ""
    assert csv_cell(None) == ""
    assert csv_cell(42) == "42"


def test_a_range_that_ends_before_it_starts_is_refused():
    with pytest.raises(PlatformRuleError) as caught:
        day_bounds(date(2026, 11, 2), date(2026, 11, 1))
    assert caught.value.code == "DATE_RANGE"


# ------------------------------------------------------------------ maintenance


def test_the_message_is_trimmed_blank_means_none_and_long_is_refused():
    assert clean_message("  Back at 9 pm  ") == "Back at 9 pm"
    assert clean_message("   ") is None
    assert clean_message(None) is None
    assert clean_message("x" * MAINTENANCE_MESSAGE_MAX) == "x" * MAINTENANCE_MESSAGE_MAX
    with pytest.raises(PlatformRuleError) as caught:
        clean_message("x" * (MAINTENANCE_MESSAGE_MAX + 1))
    assert caught.value.code == "MESSAGE_TOO_LONG"


def test_the_operator_switch_and_the_restore_flag_are_separate():
    off = effective_maintenance(operator_on=False, operator_message="ignored", restoring=False)
    assert (off.enabled, off.message, off.cause) == (False, None, None)
    on = effective_maintenance(operator_on=True, operator_message="Back at 9 pm", restoring=False)
    assert (on.enabled, on.message, on.cause) == (True, "Back at 9 pm", "operator")
    restoring = effective_maintenance(operator_on=False, operator_message=None, restoring=True)
    assert (restoring.enabled, restoring.message, restoring.cause) == (
        True,
        RESTORE_MESSAGE,
        "restore",
    )
    both = effective_maintenance(operator_on=True, operator_message="Back soon", restoring=True)
    assert both.cause == "restore"  # a restore is the stronger reason


def test_the_cached_switch_is_read_again_after_five_seconds():
    assert not cache_is_fresh(None, 100.0)
    assert cache_is_fresh(100.0, 104.9)
    assert not cache_is_fresh(100.0, 105.0)
    assert not cache_is_fresh(100.0, 99.0)  # a clock that went back reads again
