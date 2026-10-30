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
