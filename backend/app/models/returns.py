"""Credit notes (customer returns) and debit notes (returns to a supplier), Milestone 8.

Issued notes are never edited or deleted (B16). A credit note reverses part of one invoice,
with GST worked out again on the returned value."""

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.gst import SupplyKind
from app.models.base import (
    ActorMixin,
    Audited,
    Base,
    IntPK,
    Money,
    Percent,
    Quantity,
    TenantMixin,
    TimestampMixin,
)
from app.models.enums import SupplyType, str_enum


class CreditNote(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    __tablename__ = "credit_note"
    __table_args__ = (
        UniqueConstraint("tenant_id", "number"),
        Index("ix_credit_note_invoice", "invoice_id"),
    )

    id: Mapped[IntPK]
    number: Mapped[str] = mapped_column(String(16))
    financial_year: Mapped[str] = mapped_column(String(5))
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id", ondelete="RESTRICT"))
    invoice_id: Mapped[int] = mapped_column(ForeignKey("sales_invoice.id", ondelete="RESTRICT"))
    party_id: Mapped[int] = mapped_column(ForeignKey("party.id", ondelete="RESTRICT"))
    site_id: Mapped[int | None] = mapped_column(ForeignKey("site.id", ondelete="RESTRICT"))
    note_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(String(300))
    bill_to_name: Mapped[str] = mapped_column(String(150))
    bill_to_address: Mapped[str] = mapped_column(Text, default="")
    bill_to_gstin: Mapped[str | None] = mapped_column(String(15))
    place_of_supply: Mapped[str] = mapped_column(String(2))
    supply_kind: Mapped[SupplyKind] = mapped_column(str_enum(SupplyKind, "supply_kind"))
    supply_type: Mapped[SupplyType] = mapped_column(str_enum(SupplyType, "supply_type"))
    taxable_value: Mapped[Money] = mapped_column()
    cgst: Mapped[Money] = mapped_column()
    sgst: Mapped[Money] = mapped_column()
    igst: Mapped[Money] = mapped_column()
    round_off: Mapped[Money] = mapped_column()
    grand_total: Mapped[Money] = mapped_column()
    approved_by: Mapped[int | None] = mapped_column(Integer)  # owner who approved a late return

    lines: Mapped[list["CreditNoteLine"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="CreditNoteLine.line_no"
    )

    __audit_exclude__ = frozenset({"updated_at"})


class CreditNoteLine(Base, TenantMixin):
    __tablename__ = "credit_note_line"
    __table_args__ = (
        UniqueConstraint("credit_note_id", "line_no"),
        CheckConstraint("base_qty > 0", name="positive_qty"),
    )

    id: Mapped[IntPK]
    credit_note_id: Mapped[int] = mapped_column(ForeignKey("credit_note.id", ondelete="CASCADE"))
    line_no: Mapped[int] = mapped_column(Integer)
    sales_line_id: Mapped[int] = mapped_column(ForeignKey("sales_line.id", ondelete="RESTRICT"))
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id", ondelete="RESTRICT"))
    description: Mapped[str] = mapped_column(String(150))
    hsn: Mapped[str] = mapped_column(String(8))
    base_qty: Mapped[Quantity] = mapped_column()
    base_unit: Mapped[str] = mapped_column(String(16))
    rate: Mapped[Decimal] = mapped_column(Numeric(14, 6))
    taxable: Mapped[Money] = mapped_column()
    gst_rate: Mapped[Percent] = mapped_column()
    cgst: Mapped[Money] = mapped_column()
    sgst: Mapped[Money] = mapped_column()
    igst: Mapped[Money] = mapped_column()
    line_total: Mapped[Money] = mapped_column()
    restocked_at: Mapped[int | None] = mapped_column(ForeignKey("location.id", ondelete="RESTRICT"))


class DebitNote(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    __tablename__ = "debit_note"
    __table_args__ = (
        UniqueConstraint("tenant_id", "number"),
        Index("ix_debit_note_purchase", "purchase_id"),
    )

    id: Mapped[IntPK]
    number: Mapped[str] = mapped_column(String(16))
    financial_year: Mapped[str] = mapped_column(String(5))
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id", ondelete="RESTRICT"))
    purchase_id: Mapped[int] = mapped_column(ForeignKey("purchase.id", ondelete="RESTRICT"))
    party_id: Mapped[int] = mapped_column(ForeignKey("party.id", ondelete="RESTRICT"))
    note_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(String(300))
    supply_kind: Mapped[SupplyKind] = mapped_column(str_enum(SupplyKind, "supply_kind"))
    taxable_value: Mapped[Money] = mapped_column()
    cgst: Mapped[Money] = mapped_column()
    sgst: Mapped[Money] = mapped_column()
    igst: Mapped[Money] = mapped_column()
    round_off: Mapped[Money] = mapped_column()
    grand_total: Mapped[Money] = mapped_column()

    lines: Mapped[list["DebitNoteLine"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="DebitNoteLine.line_no"
    )

    __audit_exclude__ = frozenset({"updated_at"})


class DebitNoteLine(Base, TenantMixin):
    __tablename__ = "debit_note_line"
    __table_args__ = (
        UniqueConstraint("debit_note_id", "line_no"),
        CheckConstraint("base_qty > 0", name="positive_qty"),
    )

    id: Mapped[IntPK]
    debit_note_id: Mapped[int] = mapped_column(ForeignKey("debit_note.id", ondelete="CASCADE"))
    line_no: Mapped[int] = mapped_column(Integer)
    purchase_line_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_line.id", ondelete="RESTRICT")
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id", ondelete="RESTRICT"))
    description: Mapped[str] = mapped_column(String(150))
    hsn: Mapped[str] = mapped_column(String(8))
    base_qty: Mapped[Quantity] = mapped_column()
    base_unit: Mapped[str] = mapped_column(String(16))
    taxable: Mapped[Money] = mapped_column()
    gst_rate: Mapped[Percent] = mapped_column()
    cgst: Mapped[Money] = mapped_column()
    sgst: Mapped[Money] = mapped_column()
    igst: Mapped[Money] = mapped_column()
    line_total: Mapped[Money] = mapped_column()
