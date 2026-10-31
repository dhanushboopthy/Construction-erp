"""Companies (tenants) are picked by subdomain: acme.duolink.app is the company "acme" (ADR 0011).

Pure string rules, no database: what a valid company slug is, and which slug a host names.
"""

import re

# Subdomains Duolink keeps for itself. "admin" serves the platform admin (Milestone 16).
RESERVED_SLUGS = frozenset({"admin", "www", "api", "app", "mail", "static", "status", "support"})

# 3 to 30 characters: lowercase letters, digits and hyphens, not starting or ending with a hyphen.
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,28}[a-z0-9]$")


def check_slug(slug: str) -> str:
    """Return the slug trimmed and lowercased, or raise ValueError with a message for the user."""
    cleaned = slug.strip().lower()
    if not _SLUG.fullmatch(cleaned):
        raise ValueError(
            "Use 3 to 30 lowercase letters, digits or hyphens, not starting or ending with a hyphen"
        )
    if cleaned in RESERVED_SLUGS:
        raise ValueError(f"'{cleaned}' is reserved. Choose another company code")
    return cleaned


def slug_from_host(host: str | None, base_domain: str) -> str | None:
    """The company named by a host such as "acme.duolink.app:443", or None when the host is the
    bare domain, an IP address or any other name. Only one label in front of the base domain
    counts, so "www.acme.duolink.app" names nothing."""
    if not host:
        return None
    name = host.strip().lower().rsplit(":", 1)[0].rstrip(".")
    suffix = "." + base_domain.strip().lower().rstrip(".")
    if not name.endswith(suffix):
        return None
    label = name[: -len(suffix)]
    if not label or "." in label:
        return None
    return label


class StatusChangeError(ValueError):
    """A company status change that is not allowed. `code` is the API error code (409)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def status_after(current: str, action: str, *, on_trial_plan: bool) -> str:
    """The company's status after suspend, cancel or reactivate, or StatusChangeError.

    Reactivating returns a trial-plan company to `trial` and any other to `active`. A cancelled
    company is closed for good until a Super Admin reactivates it (with a reason, checked by the
    caller); its data is kept."""
    if action not in {"suspend", "cancel", "reactivate"}:
        raise ValueError(f"Unknown action {action!r}")
    if action == "reactivate":
        if current not in {"suspended", "cancelled"}:
            raise StatusChangeError("NOT_SUSPENDED", "This company is not suspended or closed")
        return "trial" if on_trial_plan else "active"
    if current == "cancelled":
        raise StatusChangeError("ALREADY_CANCELLED", "This company is already closed")
    if action == "cancel":
        return "cancelled"
    if current == "suspended":
        raise StatusChangeError("ALREADY_SUSPENDED", "This company is already suspended")
    return "suspended"
