"""System health, the notifications bell and maintenance mode (Milestone 24, ADR 0013).

Pure rules: what rings the admin's bell and how loudly, the figures the health page shows, and
which maintenance switch is in force. No database, files or clock here: the platform services
gather the signals and pass `now` in.

Two switches can close the platform to companies, and they are kept apart on purpose:

- the operator's **maintenance mode**, a persisted row, which stays on across restarts until a
  Super Admin turns it off;
- a restore's **in-memory flag** (Milestone 25), which a process that dies mid-restore forgets,
  so the platform comes back serving.
"""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Literal
from zoneinfo import ZoneInfo

BACKUP_STALE_HOURS = 26  # a nightly backup plus two hours of slack
DISK_LOW_FREE_PERCENT = 20
FAILED_ADMIN_SIGN_INS_LIMIT = 10  # in the last 24 hours; more than this rings the bell
EXPIRING_DAYS = 7
MAINTENANCE_CACHE_SECONDS = 5
MAINTENANCE_MESSAGE_MAX = 300
RESTORE_MESSAGE = "A restore is under way. The ERP will be back shortly."

_SHOP_TZ = ZoneInfo("Asia/Kolkata")  # audit filters are whole days as the shops count them
_VERSION = re.compile(r"^## (\d+\.\d+\.\d+)", re.MULTILINE)
_FORMULA_LEADS = frozenset("=+-@\t\r")


class PlatformRuleError(ValueError):
    """The rules refuse this. `code` is the API error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class Level(StrEnum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


_ORDER = {Level.CRITICAL: 0, Level.WARNING: 1, Level.INFO: 2}


@dataclass(frozen=True)
class Disk:
    name: str  # "backups" or "files"
    total_bytes: int
    free_bytes: int


@dataclass(frozen=True)
class Signals:
    """Everything the bell looks at, already counted."""

    expiring: int  # paid subscriptions ending within EXPIRING_DAYS
    expired: int  # companies whose subscription has run out (read-only)
    trials_ending: int  # trials ending within EXPIRING_DAYS
    new_tickets: int  # tickets nobody at Duolink has picked up (status open)
    urgent_tickets: int  # urgent tickets still open
    open_support_sessions: int  # support sessions still open after their token expired (M23)
    backups_watched: bool  # BACKUP_DIR is set, so the backup marker can be read
    last_backup_at: datetime | None
    disks: tuple[Disk, ...]
    failed_admin_sign_ins: int  # in the last 24 hours


@dataclass(frozen=True)
class Notification:
    id: str
    level: Level
    title: str
    body: str
    link: str


def _plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def free_percent(total_bytes: int, free_bytes: int) -> Decimal | None:
    """Free space as a percentage with one decimal; None when the size is unknown."""
    if total_bytes <= 0:
        return None
    share = Decimal(free_bytes) * 100 / Decimal(total_bytes)
    return share.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def hours_since(then: datetime | None, now: datetime) -> int | None:
    if then is None:
        return None
    return int((now - then) // timedelta(hours=1))


def backup_is_stale(last_backup_at: datetime | None, now: datetime) -> bool:
    return last_backup_at is None or now - last_backup_at > timedelta(hours=BACKUP_STALE_HOURS)


def parse_last_success(text: str) -> datetime | None:
    """`backups/.last-success` holds the Unix time of the last good backup (`date -u +%s`)."""
    value = text.strip()
    if not value.isdigit():
        return None
    return datetime.fromtimestamp(int(value), tz=UTC)


def changelog_version(text: str) -> str | None:
    """The newest release named in CHANGELOG.md (`## 1.17.0 (M24): ...`)."""
    found = _VERSION.search(text)
    return found.group(1) if found else None


def day_bounds(
    date_from: date | None, date_to: date | None
) -> tuple[datetime | None, datetime | None]:
    """A date range as instants: from the start of `date_from` to the end of `date_to`, both as
    whole days in India. Either end may be open."""
    if date_from and date_to and date_to < date_from:
        raise PlatformRuleError("DATE_RANGE", "The end date is before the start date.")
    start = (
        datetime.combine(date_from, time(), tzinfo=_SHOP_TZ).astimezone(UTC) if date_from else None
    )
    end = (
        datetime.combine(date_to + timedelta(days=1), time(), tzinfo=_SHOP_TZ).astimezone(UTC)
        if date_to
        else None
    )
    return start, end


def csv_cell(value: object) -> str:
    """A cell for the audit CSV. Text that a spreadsheet would run as a formula (=, +, -, @, a
    tab or a carriage return first) gets a leading apostrophe, so a reason typed by anyone
    stays text."""
    text = "" if value is None else str(value)
    return f"'{text}" if text[:1] in _FORMULA_LEADS else text


def notifications(signals: Signals, now: datetime) -> list[Notification]:
    """What needs Duolink's attention, most serious first. Computed on read: nothing is stored."""
    items: list[Notification] = []
    if signals.expired:
        items.append(
            Notification(
                "companies-expired",
                Level.CRITICAL,
                _plural(signals.expired, "company has expired", "companies have expired"),
                "Their plan has ended, so they are read-only until a renewal is recorded.",
                "/admin/subscriptions?status=expired",
            )
        )
    if signals.backups_watched and backup_is_stale(signals.last_backup_at, now):
        age = hours_since(signals.last_backup_at, now)
        items.append(
            Notification(
                "backup-stale",
                Level.CRITICAL,
                "No backup has been recorded"
                if age is None
                else f"The last backup is {age} hours old",
                f"A nightly backup is expected at least every {BACKUP_STALE_HOURS} hours. "
                "Check the backup service.",
                "/admin/system",
            )
        )
    for disk in signals.disks:
        free = free_percent(disk.total_bytes, disk.free_bytes)
        if free is not None and free < DISK_LOW_FREE_PERCENT:
            items.append(
                Notification(
                    f"disk-low-{disk.name}",
                    Level.CRITICAL,
                    f"The {disk.name} disk is {free}% free",
                    f"Below {DISK_LOW_FREE_PERCENT}% free. Make room before it fills up.",
                    "/admin/system",
                )
            )
    if signals.expiring:
        items.append(
            Notification(
                "subscriptions-expiring",
                Level.WARNING,
                _plural(signals.expiring, "subscription ends", "subscriptions end")
                + f" within {EXPIRING_DAYS} days",
                "Renew them before they become read-only.",
                f"/admin/subscriptions?status=active&expiring_within={EXPIRING_DAYS}",
            )
        )
    if signals.trials_ending:
        items.append(
            Notification(
                "trials-ending",
                Level.WARNING,
                _plural(signals.trials_ending, "trial ends", "trials end")
                + f" within {EXPIRING_DAYS} days",
                "Talk to these companies about a plan.",
                f"/admin/subscriptions?status=trial&expiring_within={EXPIRING_DAYS}",
            )
        )
    if signals.urgent_tickets:
        items.append(
            Notification(
                "tickets-urgent",
                Level.WARNING,
                _plural(signals.urgent_tickets, "urgent ticket is", "urgent tickets are") + " open",
                "A company marked these urgent.",
                "/admin/support?priority=urgent",
            )
        )
    if signals.open_support_sessions:
        items.append(
            Notification(
                "support-sessions-open",
                Level.WARNING,
                _plural(
                    signals.open_support_sessions,
                    "support session was",
                    "support sessions were",
                )
                + " left open",
                "The access ran out but nobody pressed Exit.",
                "/admin/audit?tab=access",
            )
        )
    if signals.failed_admin_sign_ins > FAILED_ADMIN_SIGN_INS_LIMIT:
        items.append(
            Notification(
                "admin-sign-ins-failed",
                Level.WARNING,
                f"{signals.failed_admin_sign_ins} failed admin sign-ins in 24 hours",
                "Someone may be guessing a Duolink password.",
                "/admin/audit?tab=admin&action=login_failed",
            )
        )
    if signals.new_tickets:
        items.append(
            Notification(
                "tickets-new",
                Level.INFO,
                _plural(signals.new_tickets, "new ticket is", "new tickets are") + " waiting",
                "Nobody at Duolink has picked these up yet.",
                "/admin/support?status=open",
            )
        )
    return sorted(items, key=lambda n: _ORDER[n.level])


# ------------------------------------------------------------------ maintenance


@dataclass(frozen=True)
class MaintenanceState:
    enabled: bool
    message: str | None
    cause: Literal["operator", "restore"] | None


def clean_message(text: str | None) -> str | None:
    """The message companies see ("Back at 9 pm"). Optional; blank means none."""
    value = (text or "").strip()
    if len(value) > MAINTENANCE_MESSAGE_MAX:
        raise PlatformRuleError(
            "MESSAGE_TOO_LONG", f"Keep the message to {MAINTENANCE_MESSAGE_MAX} characters."
        )
    return value or None


def effective_maintenance(
    *, operator_on: bool, operator_message: str | None, restoring: bool
) -> MaintenanceState:
    """Which switch is in force. A restore wins: its message says what is really happening."""
    if restoring:
        return MaintenanceState(True, RESTORE_MESSAGE, "restore")
    if operator_on:
        return MaintenanceState(True, operator_message, "operator")
    return MaintenanceState(False, None, None)


def cache_is_fresh(loaded_at: float | None, now: float) -> bool:
    """The switch is read from the database at most every MAINTENANCE_CACHE_SECONDS."""
    return loaded_at is not None and 0 <= now - loaded_at < MAINTENANCE_CACHE_SECONDS
