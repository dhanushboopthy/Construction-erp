"""Bill designs per company (Milestone 28, ADR 0013).

A design is HTML that Duolink uploads for one of the company's document slots. The HTML is data
with a placeholder grammar, never a Jinja template (`app/domain/bill_template.py`). A version is
never edited: a new upload is the next version of its slot. A document pins the version it was
issued with (`bill_template_id` on the document tables), so it reprints on that design.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ActorMixin, Audited, Base, IntPK, TenantMixin, TimestampMixin
from app.models.enums import BillSlot, str_enum


class BillTemplate(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    __tablename__ = "bill_template"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slot", "version"),
        # One active design per slot per company.
        Index(
            "uq_bill_template_active_slot",
            "tenant_id",
            "slot",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[IntPK]
    slot: Mapped[BillSlot] = mapped_column(str_enum(BillSlot, "bill_slot"))
    name: Mapped[str] = mapped_column(String(120))
    version: Mapped[int] = mapped_column(Integer)  # per company and slot
    html_key: Mapped[str] = mapped_column(String(200))  # the cleaned HTML, in storage
    html_sha256: Mapped[str] = mapped_column(String(64))
    html_size: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    uploaded_by_admin_id: Mapped[int | None] = mapped_column(ForeignKey("platform_admin.id"))
    # What cleaning took out of the upload (a list of short sentences).
    removed: Mapped[list[str]] = mapped_column(JSON, default=list)
    # The company's second logo as it was when this version was set up (see
    # `services/bill_templates.py`); all three together or none.
    secondary_logo_key: Mapped[str | None] = mapped_column(String(200))
    secondary_logo_type: Mapped[str | None] = mapped_column(String(20))
    secondary_logo_sha256: Mapped[str | None] = mapped_column(String(64))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __audit_exclude__ = frozenset({"updated_at", "removed"})


class BillTemplateAsset(Base, TenantMixin, TimestampMixin):
    """An image a design uses (a stamp, a signature). It lives and dies with its version."""

    __tablename__ = "bill_template_asset"
    __table_args__ = (UniqueConstraint("template_id", "name"),)

    id: Mapped[IntPK]
    template_id: Mapped[int] = mapped_column(
        ForeignKey("bill_template.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80))
    content_type: Mapped[str] = mapped_column(String(20))
    key: Mapped[str] = mapped_column(String(200))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)


__all__ = ["BillTemplate", "BillTemplateAsset"]
