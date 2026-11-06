"""A user's own keyboard shortcuts (they edit them with Ctrl+Shift+Alt+1).

Only what a user changed is stored: one row per action whose shortcut differs from the default,
which the frontend keeps. So a new action, or a changed default, reaches everyone who has not
touched it.
"""

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ActorMixin, Audited, Base, IntPK, TenantMixin, TimestampMixin


class UserShortcut(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    __tablename__ = "user_shortcut"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "action_id"),
        # One combination runs one action, per user.
        UniqueConstraint("tenant_id", "user_id", "combo"),
    )

    id: Mapped[IntPK]
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    action_id: Mapped[str] = mapped_column(String(60))  # "go:/items", "new"
    combo: Mapped[str] = mapped_column(String(16))  # "Alt+N", "Alt+Shift+7"
