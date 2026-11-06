from fastapi import APIRouter, status

from app.api.deps import CurrentPrincipal, DbSession
from app.schemas.shortcuts import ShortcutsIn, ShortcutsOut
from app.services import shortcuts as shortcut_service

router = APIRouter(prefix="/me/shortcuts", tags=["shortcuts"])


@router.get("", response_model=ShortcutsOut)
def my_shortcuts(principal: CurrentPrincipal, db: DbSession) -> ShortcutsOut:
    """What the signed-in user changed. Any role, for themselves only."""
    return ShortcutsOut(items=shortcut_service.list_for(db, principal.user_id))


@router.put("", response_model=ShortcutsOut)
def save_my_shortcuts(
    body: ShortcutsIn, principal: CurrentPrincipal, db: DbSession
) -> ShortcutsOut:
    """Replace the user's changes. Actions left out go back to their default."""
    return ShortcutsOut(items=shortcut_service.replace(db, principal.user_id, body.items))


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def reset_my_shortcuts(principal: CurrentPrincipal, db: DbSession) -> None:
    """Restore every default."""
    shortcut_service.replace(db, principal.user_id, [])
