"""A user's own keyboard shortcuts. One transaction per call; each user reads and writes only
their own rows."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import UnprocessableError
from app.core.tenancy import current_tenant_id
from app.domain.shortcuts import ShortcutError, validate_set
from app.models.shortcuts import UserShortcut
from app.schemas.shortcuts import ShortcutItem


def list_for(db: Session, user_id: int) -> list[ShortcutItem]:
    rows = db.execute(
        select(UserShortcut)
        .where(UserShortcut.tenant_id == current_tenant_id(db), UserShortcut.user_id == user_id)
        .order_by(UserShortcut.action_id)
    ).scalars()
    return [ShortcutItem(action_id=r.action_id, combo=r.combo) for r in rows]


def replace(db: Session, user_id: int, items: list[ShortcutItem]) -> list[ShortcutItem]:
    """Make `items` the user's changes, replacing what was there (an empty list restores every
    default). Refuses a bad or duplicated combination with a 422 naming the action."""
    try:
        checked = validate_set((i.action_id, i.combo) for i in items)
    except ShortcutError as error:
        raise UnprocessableError(str(error), code="INVALID_SHORTCUT", field=error.field) from None
    tenant_id = current_tenant_id(db)
    # Delete first and in its own statement: the ORM would insert before it deletes, and a user
    # who swaps two combinations would trip the unique constraint.
    db.execute(
        delete(UserShortcut).where(
            UserShortcut.tenant_id == tenant_id, UserShortcut.user_id == user_id
        )
    )
    for action_id, combo in checked:
        db.add(UserShortcut(tenant_id=tenant_id, user_id=user_id, action_id=action_id, combo=combo))
    db.commit()
    return list_for(db, user_id)
