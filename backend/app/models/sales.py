"""Sales invoices (Milestone 6). Every invoice is a real GST tax invoice (ADR 0005); it is
never edited or deleted, only corrected by credit notes (Milestone 8)."""

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
from app.domain.pricing import RateSource
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
    UnitCost,
)
from app.models.enums import FulfilmentSource, InvoiceStatus, SupplyType, str_enum


class SalesInvoice(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    __tablename__ = "sales_invoice"
    __table_args__ = (
        UniqueConstraint("tenant_id", "number"),
        UniqueConstraint("tenant_id", "idempotency_key"),
        Index("ix_sales_invoice_date", "invoice_date"),
        Index("ix_sales_invoice_party", "party_id", "invoice_date"),
    )

    id: Mapped[IntPK]
    number: Mapped[str] = mapped_column(String(16))
    financial_year: Mapped[str] = mapped_column(String(5))
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id", ondelete="RESTRICT"))
    party_id: Mapped[int] = mapped_column(ForeignKey("party.id", ondelete="RESTRICT"))
    site_id: Mapped[int | None] = mapped_column(ForeignKey("site.id", ondelete="RESTRICT"))
    # What was printed on the bill, kept as text so later edits to the party never change it.
    bill_to_name: Mapped[str] = mapped_column(String(150))
    bill_to_address: Mapped[str] = mapped_column(Text, default="")
    bill_to_gstin: Mapped[str | None] = mapped_column(String(15))
    ship_to_name: Mapped[str | None] = mapped_column(String(150))
    ship_to_address: Mapped[str | None] = mapped_column(Text)
    ship_to_gstin: Mapped[str | None] = mapped_column(String(15))  # null means "URP" (G13)
    place_of_supply: Mapped[str] = mapped_column(String(2))
    supply_kind: Mapped[SupplyKind] = mapped_column(str_enum(SupplyKind, "supply_kind"))
    supply_type: Mapped[SupplyType] = mapped_column(str_enum(SupplyType, "supply_type"))
    invoice_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    taxable_value: Mapped[Money] = mapped_column()
    cgst: Mapped[Money] = mapped_column()
    sgst: Mapped[Money] = mapped_column()
    igst: Mapped[Money] = mapped_column()
    round_off: Mapped[Money] = mapped_column()
    grand_total: Mapped[Money] = mapped_column()
    pending_balance_at_billing: Mapped[Money] = mapped_column()
    vehicle_no: Mapped[str | None] = mapped_column(String(20))
    remark: Mapped[str | None] = mapped_column(String(300))
    idempotency_key: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[InvoiceStatus] = mapped_column(
        str_enum(InvoiceStatus, "invoice_status"), default=InvoiceStatus.POSTED
    )

    lines: Mapped[list["SalesLine"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="SalesLine.line_no"
    )

    __audit_exclude__ = frozenset({"updated_at"})


class SalesLine(Base, TenantMixin):
    __tablename__ = "sales_line"
    __table_args__ = (
        UniqueConstraint("invoice_id", "line_no"),
        CheckConstraint("base_qty > 0", name="positive_qty"),
    )

    id: Mapped[IntPK]
    invoice_id: Mapped[int] = mapped_column(ForeignKey("sales_invoice.id", ondelete="CASCADE"))
    line_no: Mapped[int] = mapped_column(Integer)
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id", ondelete="RESTRICT"))
    description: Mapped[str] = mapped_column(String(150))
    hsn: Mapped[str] = mapped_column(String(8))
    unit: Mapped[str] = mapped_column(String(16))  # the unit the customer asked in
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    base_qty: Mapped[Quantity] = mapped_column()
    base_unit: Mapped[str] = mapped_column(String(16))
    rate: Mapped[Decimal] = mapped_column(Numeric(14, 6))  # per base unit, excluding GST
    rate_source: Mapped[RateSource] = mapped_column(str_enum(RateSource, "rate_source"))
    discount: Mapped[Money] = mapped_column()
    discount_reason: Mapped[str | None] = mapped_column(String(200))
    taxable: Mapped[Money] = mapped_column()
    gst_rate: Mapped[Percent] = mapped_column()
    cgst: Mapped[Money] = mapped_column()
    sgst: Mapped[Money] = mapped_column()
    igst: Mapped[Money] = mapped_column()
    line_total: Mapped[Money] = mapped_column()
    fulfilment_source: Mapped[FulfilmentSource] = mapped_column(
        str_enum(FulfilmentSource, "fulfilment_source")
    )
    source_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("location.id", ondelete="RESTRICT")
    )
    stock_after: Mapped[Quantity | None] = mapped_column()  # left at the source after this sale
    cost_per_unit: Mapped[UnitCost] = mapped_column()  # average cost at the time: owner only
