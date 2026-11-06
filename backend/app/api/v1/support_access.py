"""Duolink support access (Milestone 23, ADR 0013).

`/support-access`: the owner's Settings. Only the owner in person: never a counter or accountant,
and never a Duolink support session reading as an owner (403 SUPPORT_READ_ONLY), so the session
cannot see or touch the grant that governs it. Grant and revoke work while the company is
read-only: revoking must always be possible.

`/support-session`: the Duolink admin inside the company. Its status (for the banner) and Exit,
the one write a support session may make.
"""

from fastapi import APIRouter, status

from app.api.deps import CurrentTenant, DbSession, OwnerInPerson, SupportPrincipal
from app.schemas.support_access import (
    AccessOverview,
    GrantCreate,
    GrantOut,
    SessionEventOut,
    SessionRow,
    SupportSessionStatus,
)
from app.services import support_access as service

router = APIRouter(tags=["support access"])


@router.get("/support-access", response_model=AccessOverview)
def overview(_: OwnerInPerson, db: DbSession) -> AccessOverview:
    """The live grant (or none), with the time left, and the last few grants."""
    return service.overview(db)


@router.post("/support-access/grants", response_model=GrantOut, status_code=status.HTTP_201_CREATED)
def grant(body: GrantCreate, owner: OwnerInPerson, db: DbSession) -> GrantOut:
    """Let Duolink in, read-only, for 1, 4, 24 or 72 hours. A live grant is replaced: it is
    recorded as revoked and any Duolink session under it ends. 404 TICKET_NOT_FOUND."""
    return service.grant(db, owner.user_id, body)


@router.post("/support-access/revoke", response_model=GrantOut)
def revoke(owner: OwnerInPerson, db: DbSession) -> GrantOut:
    """End the live grant now. Duolink's next request answers 401. 409 NO_LIVE_GRANT."""
    return service.revoke(db, owner.user_id)


@router.get("/support-access/sessions", response_model=list[SessionRow])
def history(_: OwnerInPerson, db: DbSession) -> list[SessionRow]:
    """Who from Duolink entered, when, for how long, and how many requests they made."""
    return service.history(db)


@router.get(
    "/support-access/sessions/{support_session_id}/events",
    response_model=list[SessionEventOut],
)
def events(support_session_id: int, _: OwnerInPerson, db: DbSession) -> list[SessionEventOut]:
    """Every request of one visit: method and path, and whether it was a refused write."""
    return service.session_events(db, support_session_id)


@router.get("/support-session", response_model=SupportSessionStatus)
def session_status(
    principal: SupportPrincipal, tenant: CurrentTenant, db: DbSession
) -> SupportSessionStatus:
    """The support session this token belongs to: company, admin, when it ends."""
    assert principal.support is not None  # noqa: S101 - SupportPrincipal guarantees it
    return service.status(db, tenant, principal.support)


@router.post("/support-session/exit", status_code=status.HTTP_204_NO_CONTENT)
def exit_session(principal: SupportPrincipal, db: DbSession) -> None:
    """Leave the company. The token answers 401 from the next request on."""
    assert principal.support is not None  # noqa: S101 - SupportPrincipal guarantees it
    service.exit_session(db, principal.support)
