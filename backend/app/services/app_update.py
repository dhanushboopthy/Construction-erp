"""The release generation, as a company's address reads it (Milestone 29).

Every open browser reads it with GET /tenant and, when it changes, asks its service worker to
look for a new build. It is the platform's one row, not company data, so a company session may
read it; only `services/platform/app_update.py` changes it.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.platform import PlatformAppUpdate


def generation(db: Session) -> int:
    """The current release generation; 0 until a Super Admin first forces an update."""
    value = db.execute(
        select(PlatformAppUpdate.generation).where(PlatformAppUpdate.id == 1)
    ).scalar_one_or_none()
    return value or 0
