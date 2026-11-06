"""Counters for gapless document numbers: one per location, document type and financial year."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, PrimaryKeyConstraint, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin
from app.models.enums import DocType, SequenceChange, str_enum


class DocumentSequence(Base, TenantMixin):
    __tablename__ = "document_sequence"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "location_id", "doc_type", "financial_year"),
    )

    location_id: Mapped[int] = mapped_column(ForeignKey("location.id", ondelete="RESTRICT"))
    doc_type: Mapped[DocType] = mapped_column(str_enum(DocType, "doc_type"))
    financial_year: Mapped[str] = mapped_column(String(5))  # e.g. "26-27"
    next_value: Mapped[int] = mapped_column(Integer, default=1)


class DocumentSequenceEvent(Base, TenantMixin):
    """Append-only: one row each time a Super Admin set a series, or a data deletion reset it
    (Milestone 26). The integrity check reads it to accept the gap a change explains."""

    __tablename__ = "document_sequence_event"
    __table_args__ = (
        Index(
            "ix_document_sequence_event_series",
            "tenant_id",
            "location_id",
            "doc_type",
            "financial_year",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id", ondelete="RESTRICT"))
    doc_type: Mapped[DocType] = mapped_column(str_enum(DocType, "doc_type"))
    financial_year: Mapped[str] = mapped_column(String(5))
    change: Mapped[SequenceChange] = mapped_column(str_enum(SequenceChange, "sequence_change"))
    from_value: Mapped[int] = mapped_column(Integer)
    to_value: Mapped[int] = mapped_column(Integer)
    floor_value: Mapped[int] = mapped_column(Integer)  # highest existing + 1 at the time
    reason: Mapped[str] = mapped_column(String(300))
    admin_id: Mapped[int | None] = mapped_column(Integer)  # the platform admin (no foreign key)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CompanyCounter(Base, TenantMixin):
    """A gapless counter for something that belongs to the company, not to a shop (support
    tickets, Milestone 22). One row per company and name."""

    __tablename__ = "company_counter"
    __table_args__ = (PrimaryKeyConstraint("tenant_id", "name"),)

    name: Mapped[str] = mapped_column(String(30))
    next_value: Mapped[int] = mapped_column(Integer, default=1)
