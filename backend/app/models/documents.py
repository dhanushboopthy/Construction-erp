"""Files kept against a document: weighbridge slips and delivery proof (B17, Milestone 11).
The bytes live in a `Storage` (services/storage); this row says what they belong to. Rows are
never deleted: a wrong upload is explained by a newer one."""

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ActorMixin, Audited, Base, IntPK, TenantMixin, TimestampMixin
from app.models.enums import AttachmentKind, AttachmentRef, str_enum


class Attachment(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    __tablename__ = "attachment"
    __table_args__ = (Index("ix_attachment_ref", "ref_type", "ref_id"),)

    id: Mapped[IntPK]
    ref_type: Mapped[AttachmentRef] = mapped_column(str_enum(AttachmentRef, "attachment_ref"))
    ref_id: Mapped[int] = mapped_column(Integer)
    kind: Mapped[AttachmentKind] = mapped_column(str_enum(AttachmentKind, "attachment_kind"))
    file_name: Mapped[str] = mapped_column(String(150))  # as uploaded, for display only
    content_type: Mapped[str] = mapped_column(String(60))  # decided from the bytes, not the client
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(200))
    location_id: Mapped[int | None] = mapped_column(ForeignKey("location.id", ondelete="RESTRICT"))
    note: Mapped[str | None] = mapped_column(String(200))

    __audit_exclude__ = frozenset({"updated_at"})
