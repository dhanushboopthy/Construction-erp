"""Rules for Duolink's user support tools (Milestone 19).

Pure rules, no database or clock: the service reads the counts and the time and passes them in.
"""

from datetime import datetime


class UserRuleError(ValueError):
    """A support action that is not allowed. `code` is the API error code (409)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def confirmation_matches(typed: str, expected: str) -> bool:
    """A typed confirmation must be exactly what was asked for: case matters, nothing is
    trimmed (ADR 0013, rule 5)."""
    return typed == expected


def check_removal(*, is_owner: bool, is_active: bool, active_owners: int) -> None:
    """A company always keeps one active owner, so the last one cannot be removed."""
    if is_owner and is_active and active_owners <= 1:
        raise UserRuleError("LAST_OWNER", "There must always be at least one active owner")


def check_not_removed(removed_at: datetime | None) -> None:
    """A removed account is only a name on old documents: nothing changes it any more."""
    if removed_at is not None:
        raise UserRuleError("USER_REMOVED", "This account has been removed")


def session_is_live(revoked_at: datetime | None, expires_at: datetime, now: datetime) -> bool:
    return revoked_at is None and expires_at > now


# Order matters: Edge and Chrome both say "Chrome"; iPhone and Android both say another system.
_BROWSERS = (
    ("Edg/", "Edge"),
    ("Firefox/", "Firefox"),
    ("Chrome/", "Chrome"),
    ("Safari/", "Safari"),
)
_SYSTEMS = (
    ("iPhone", "iPhone"),
    ("iPad", "iPad"),
    ("Android", "Android"),
    ("CrOS", "ChromeOS"),
    ("Windows", "Windows"),
    ("Macintosh", "macOS"),
    ("Linux", "Linux"),
)


def device_label(user_agent: str | None) -> str:
    """ "Chrome on Windows" from a browser's User-Agent text, for the sessions list."""
    if not user_agent:
        return "Unknown device"
    browser = next((name for mark, name in _BROWSERS if mark in user_agent), None)
    if browser is None:
        return "Unknown browser"
    system = next((name for mark, name in _SYSTEMS if mark in user_agent), None)
    return f"{browser} on {system}" if system else browser
