"""Counters for gapless document numbers: one per location, document type and financial year."""

from sqlalchemy import ForeignKey, Integer, PrimaryKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin
from app.models.enums import DocType, str_enum


class DocumentSequence(Base, TenantMixin):
    __tablename__ = "document_sequence"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "location_id", "doc_type", "financial_year"),
    )

    location_id: Mapped[int] = mapped_column(ForeignKey("location.id", ondelete="RESTRICT"))
    doc_type: Mapped[DocType] = mapped_column(str_enum(DocType, "doc_type"))
    financial_year: Mapped[str] = mapped_column(String(5))  # e.g. "26-27"
    next_value: Mapped[int] = mapped_column(Integer, default=1)
