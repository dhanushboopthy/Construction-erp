"""What a company may do while its subscription has run out (Milestone 21, ADR 0013).

A read-only company can still read, report and download its books, but cannot write. The check
runs on every request, so a renewal takes effect at once with no sign-out. Suspended and closed
companies are refused earlier, in `tenants.check_open`.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import PermissionDeniedError
from app.domain.subscriptions import AccessState, access_state, days_left, effective_status
from app.models.billing import Subscription
from app.models.tenancy import Tenant

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# The one place that lists what a read-only company may still write: (method, path pattern).
# Later milestones add their entries here (M22: raise a support ticket; M30: renew online).
READ_ONLY_EXCEPTIONS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("POST", re.compile(r"^/api/v1/auth/login$")),
    ("POST", re.compile(r"^/api/v1/auth/refresh$")),
    ("POST", re.compile(r"^/api/v1/auth/logout$")),
    ("POST", re.compile(r"^/api/v1/auth/change-password$")),
    # Milestone 22: a company that cannot save can still ask Duolink for help.
    ("POST", re.compile(r"^/api/v1/support/tickets$")),
    ("POST", re.compile(r"^/api/v1/support/tickets/\d+/(reply|close)$")),
    # Milestone 23: the owner can always let Duolink in, and always shut it out; and a Duolink
    # support session (read-only in any case) can always leave.
    ("POST", re.compile(r"^/api/v1/support-access/(grants|revoke)$")),
    ("POST", re.compile(r"^/api/v1/support-session/exit$")),
    # Milestone 30: an expired company's owner can renew online, and the payment lands. (The
    # webhook takes no company from the address, so it never reaches this check.)
    ("POST", re.compile(r"^/api/v1/subscription/(orders|verify)$")),
)


@dataclass(frozen=True)
class CompanyAccess:
    state: AccessState
    subscription_status: str | None  # trial, active, expired or cancelled
    expires_at: datetime | None
    days_left: int | None


def subscription_of(db: Session, tenant_id: int) -> Subscription | None:
    return db.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    ).scalar_one_or_none()


def access_of(tenant: Tenant, subscription: Subscription | None, now: datetime) -> CompanyAccess:
    if subscription is None:  # every company has one; a script-made company may not yet
        state = access_state(
            company_status=tenant.status.value,
            subscription_status="active",
            expires_at=None,
            now=now,
        )
        return CompanyAccess(state, None, None, None)
    return CompanyAccess(
        access_state(
            company_status=tenant.status.value,
            subscription_status=subscription.status.value,
            expires_at=subscription.expires_at,
            now=now,
        ),
        effective_status(subscription.status.value, subscription.expires_at, now),
        subscription.expires_at,
        days_left(subscription.expires_at, now),
    )


def is_excepted(method: str, path: str) -> bool:
    return method in SAFE_METHODS or any(
        method == m and pattern.match(path) for m, pattern in READ_ONLY_EXCEPTIONS
    )


def enforce(db: Session, tenant: Tenant, method: str, path: str) -> None:
    """403 SUBSCRIPTION_EXPIRED for a write by a company whose subscription has run out."""
    if is_excepted(method, path):
        return
    access = access_of(tenant, subscription_of(db, tenant.id), datetime.now(UTC))
    if access.state is AccessState.READ_ONLY:
        raise PermissionDeniedError(
            "Your Duolink plan has ended, so this company is read-only. You can still read and "
            "download your books. Contact Duolink to renew.",
            code="SUBSCRIPTION_EXPIRED",
        )
