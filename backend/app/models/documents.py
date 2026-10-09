"""Files kept against a document: weighbridge slips and delivery proof (B17, Milestone 11).
The bytes live in a `Storage` (services/storage); this row says what they belong to. Rows are
never deleted: a wrong upload is explained by a newer one."""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ActorMixin, Audited, Base, IntPK, Money, TenantMixin, TimestampMixin
from app.models.enums import AttachmentKind, AttachmentRef, ClosingStatus, str_enum


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


class DailyClosing(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    """One shop's day: the figures, the cash count and the PDF (B12, G17, Milestone 12).
    Once `closed`, documents dated that day at that shop are refused until the owner reopens it."""

    __tablename__ = "daily_closing"
    __table_args__ = (UniqueConstraint("tenant_id", "location_id", "closing_date"),)

    id: Mapped[IntPK]
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id", ondelete="RESTRICT"))
    closing_date: Mapped[date] = mapped_column(Date)
    status: Mapped[ClosingStatus] = mapped_column(
        str_enum(ClosingStatus, "closing_status"), default=ClosingStatus.CLOSED
    )
    invoices_count: Mapped[int] = mapped_column(Integer)
    sales_total: Mapped[Money] = mapped_column()
    returns_total: Mapped[Money] = mapped_column()
    opening_cash: Mapped[Money] = mapped_column()
    cash_in: Mapped[Money] = mapped_column()
    cash_out: Mapped[Money] = mapped_column()
    expected_cash: Mapped[Money] = mapped_column()
    counted_cash: Mapped[Money] = mapped_column()
    difference: Mapped[Money] = mapped_column()
    note: Mapped[str | None] = mapped_column(String(300))
    closed_by: Mapped[int | None] = mapped_column(Integer)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pdf_key: Mapped[str | None] = mapped_column(String(200))
    reopened_by: Mapped[int | None] = mapped_column(Integer)
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopen_reason: Mapped[str | None] = mapped_column(String(300))
    times_closed: Mapped[int] = mapped_column(Integer, default=1)

    __audit_exclude__ = frozenset({"updated_at"})
