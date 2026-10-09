"""E-way bills and e-invoices (IRN) for issued sales invoices, Milestone 10. The provider's raw
answers are kept (G12) so a dispute can be traced. These rows are never deleted: a cancelled
bill stays as a cancelled row."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ActorMixin, Audited, Base, IntPK, TenantMixin, TimestampMixin
from app.models.enums import ComplianceStatus, EwaySource, str_enum


class EwayBill(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    __tablename__ = "eway_bill"
    __table_args__ = (
        UniqueConstraint("tenant_id", "number"),
        # Only one live e-way bill per invoice; a cancelled one may be followed by a new one.
        Index(
            "uq_eway_bill_live_invoice",
            "invoice_id",
            unique=True,
            postgresql_where=text("status = 'generated'"),
        ),
    )

    id: Mapped[IntPK]
    invoice_id: Mapped[int] = mapped_column(ForeignKey("sales_invoice.id", ondelete="RESTRICT"))
    number: Mapped[str] = mapped_column(String(12))
    status: Mapped[ComplianceStatus] = mapped_column(
        str_enum(ComplianceStatus, "compliance_status"), default=ComplianceStatus.GENERATED
    )
    source: Mapped[EwaySource] = mapped_column(str_enum(EwaySource, "eway_source"))
    vehicle_no: Mapped[str | None] = mapped_column(String(20))
    from_pincode: Mapped[str | None] = mapped_column(String(6))
    to_pincode: Mapped[str | None] = mapped_column(String(6))
    distance_km: Mapped[int | None] = mapped_column(Integer)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[date | None] = mapped_column()
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(200))
    # Every call made for this bill with the provider's answer, oldest first.
    responses: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)

    __audit_exclude__ = frozenset({"updated_at", "responses"})


class EInvoice(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    __tablename__ = "einvoice"
    __table_args__ = (UniqueConstraint("tenant_id", "invoice_id"), UniqueConstraint("irn"))

    id: Mapped[IntPK]
    invoice_id: Mapped[int] = mapped_column(ForeignKey("sales_invoice.id", ondelete="RESTRICT"))
    irn: Mapped[str] = mapped_column(String(64))
    ack_no: Mapped[str] = mapped_column(String(20))
    ack_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    signed_qr: Mapped[str] = mapped_column(Text)
    status: Mapped[ComplianceStatus] = mapped_column(
        str_enum(ComplianceStatus, "compliance_status"), default=ComplianceStatus.GENERATED
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(200))
    responses: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)

    __audit_exclude__ = frozenset({"updated_at", "responses", "signed_qr"})
