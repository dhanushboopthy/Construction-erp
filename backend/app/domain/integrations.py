"""Duolink's shared integrations: the GSP (e-way bill and IRN) and the GSTIN lookup
(Milestone 27, ADR 0013 point 7).

Pure rules: which credentials a provider needs, how a saved key is shown (its last 4 characters
only), how a failure message is cleaned of secrets, the per-company limits, when a cached lookup
is still fresh, and the Indian day, week and month the usage is counted in.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo

KINDS = ("gsp", "gstin_lookup")
PROVIDERS = ("fake", "sandbox", "live")
OUTCOMES = ("ok", "failed", "cached", "blocked")
STATUSES = ("not_connected", "connected", "failing")
# Outcomes that reached the provider, so they use up a company's allowance.
COUNTED = frozenset({"ok", "failed"})

_FIELDS = {
    "gsp": ("client_id", "client_secret", "username", "password"),
    "gstin_lookup": ("api_key",),
}
_KEY_FIELD = {"gsp": "client_secret", "gstin_lookup": "api_key"}
MIN_KEY_LENGTH = 8  # shorter, and the last 4 characters would give half of it away
FAILURE_MESSAGE_LENGTH = 200
MAX_LIMIT = 100_000
MAX_CACHE_HOURS = 24 * 365


class IntegrationRuleError(ValueError):
    """The integration rules refuse this. `code` is the API error code."""

    def __init__(self, code: str, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field


def _check_kind(kind: str) -> None:
    if kind not in KINDS:
        raise IntegrationRuleError("INTEGRATION_KIND_UNKNOWN", f"Not an integration: {kind}.")


def _check_provider_name(provider: str) -> None:
    if provider not in PROVIDERS:
        raise IntegrationRuleError("PROVIDER_UNKNOWN", f"Not a provider: {provider}.")


# ------------------------------------------------------------------ credentials


def credential_fields(kind: str, provider: str) -> tuple[str, ...]:
    """The fields a provider needs. The pretend provider needs none."""
    _check_kind(kind)
    _check_provider_name(provider)
    return () if provider == "fake" else _FIELDS[kind]


def key_field(kind: str) -> str:
    """The credential whose last 4 characters are shown to tell one key from another."""
    _check_kind(kind)
    return _KEY_FIELD[kind]


def key_last4(secret: str) -> str:
    if len(secret) < MIN_KEY_LENGTH:
        raise IntegrationRuleError(
            "KEY_TOO_SHORT", f"A key has at least {MIN_KEY_LENGTH} characters."
        )
    return secret[-4:]


def merge_credentials(
    kind: str, provider: str, stored: Mapping[str, str], given: Mapping[str, str]
) -> dict[str, str]:
    """The credentials to save. A blank field keeps the saved value, so an admin changing one
    setting never has to type a key back in (and the key is never sent to the browser)."""
    fields = credential_fields(kind, provider)
    merged: dict[str, str] = {}
    for name in fields:
        value = (given.get(name) or "").strip() or stored.get(name, "")
        if not value:
            raise IntegrationRuleError(
                "CREDENTIALS_MISSING", f"Enter the {name.replace('_', ' ')}.", field=name
            )
        merged[name] = value
    if fields:
        name = key_field(kind)
        if len(merged[name]) < MIN_KEY_LENGTH:
            raise IntegrationRuleError(
                "KEY_TOO_SHORT",
                f"The {name.replace('_', ' ')} has at least {MIN_KEY_LENGTH} characters.",
                field=name,
            )
    return merged


def check_base_url(provider: str, base_url: str) -> str:
    """The provider's address without a trailing slash. A live provider is reached over HTTPS
    only; the pretend provider has no address."""
    _check_provider_name(provider)
    if provider == "fake":
        return ""
    url = base_url.strip().rstrip("/")
    if not url:
        raise IntegrationRuleError(
            "BASE_URL_REQUIRED", "Enter the provider's address.", field="base_url"
        )
    scheme, _, rest = url.partition("://")
    if scheme not in {"http", "https"} or not rest:
        raise IntegrationRuleError(
            "BASE_URL_INVALID", "The address starts with https://.", field="base_url"
        )
    if provider == "live" and scheme != "https":
        raise IntegrationRuleError(
            "BASE_URL_NOT_HTTPS", "A live provider is reached over https:// only.", field="base_url"
        )
    return url


def check_provider(provider: str, *, is_production: bool) -> None:
    _check_provider_name(provider)
    if provider == "fake" and is_production:
        raise IntegrationRuleError(
            "FAKE_NOT_IN_PRODUCTION",
            "The pretend provider is never used in production.",
            field="provider",
        )


def scrub(message: str, secrets: Iterable[str]) -> str:
    """A provider's failure message as it may be stored and shown: every secret replaced,
    whitespace collapsed, cut to FAILURE_MESSAGE_LENGTH characters."""
    for secret in secrets:
        if len(secret) >= 4:
            message = message.replace(secret, "****")
    return " ".join(message.split())[:FAILURE_MESSAGE_LENGTH]


# ------------------------------------------------------------------ limits and status


@dataclass(frozen=True)
class Limits:
    """Per company: provider calls a day and a month, when to warn, and how long a GSTIN
    lookup is reused from the cache."""

    daily: int
    monthly: int
    warn_at_percent: int
    cache_hours: int


def check_limits(limits: Limits) -> Limits:
    def bad(field: str, message: str) -> IntegrationRuleError:
        return IntegrationRuleError("LIMIT_INVALID", message, field=field)

    if not 1 <= limits.daily <= MAX_LIMIT:
        raise bad("daily", f"The daily limit is 1 to {MAX_LIMIT}.")
    if not 1 <= limits.monthly <= MAX_LIMIT:
        raise bad("monthly", f"The monthly limit is 1 to {MAX_LIMIT}.")
    if not 1 <= limits.warn_at_percent <= 100:
        raise bad("warn_at_percent", "Warn at 1 to 100 per cent.")
    if not 0 <= limits.cache_hours <= MAX_CACHE_HOURS:
        raise bad("cache_hours", f"Keep lookups 0 to {MAX_CACHE_HOURS} hours.")
    if limits.daily > limits.monthly:
        raise IntegrationRuleError(
            "LIMIT_DAILY_OVER_MONTHLY",
            "The daily limit cannot be more than the monthly limit.",
            field="daily",
        )
    return limits


def status_of(
    *, connected: bool, last_success_at: datetime | None, last_failure_at: datetime | None
) -> str:
    if not connected:
        return "not_connected"
    if last_failure_at is not None and (
        last_success_at is None or last_failure_at > last_success_at
    ):
        return "failing"
    return "connected"


def near_limit(used: int, limit: int, warn_at_percent: int) -> bool:
    return used * 100 >= limit * warn_at_percent


def remaining(used: int, limit: int) -> int:
    return max(limit - used, 0)


# ------------------------------------------------------------------ the GSTIN lookup


def is_fresh(fetched_at: datetime | None, now: datetime, cache_hours: int) -> bool:
    return fetched_at is not None and now - fetched_at < timedelta(hours=cache_hours)


def lookup_decision(*, fresh: bool, used_today: int, used_month: int, limits: Limits) -> str:
    """ "cached" (no provider call, no allowance used), "blocked" (over a limit) or "call"."""
    if fresh:
        return "cached"
    if used_today >= limits.daily or used_month >= limits.monthly:
        return "blocked"
    return "call"


@dataclass(frozen=True)
class Windows:
    day: datetime
    week: datetime  # Monday
    month: datetime


def usage_windows(today: date, tz: tzinfo) -> Windows:
    """Where today, this week and this month began, in the shop's time zone."""

    def start(d: date) -> datetime:
        return datetime.combine(d, time(0), tzinfo=tz)

    return Windows(
        day=start(today),
        week=start(today - timedelta(days=today.weekday())),
        month=start(today.replace(day=1)),
    )
