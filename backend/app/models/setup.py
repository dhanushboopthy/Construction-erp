"""Setup tables: shop settings, locations, users and their location assignments."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    ActorMixin,
    Audited,
    Base,
    IntPK,
    Money,
    Percent,
    TenantMixin,
    TimestampMixin,
)
from app.models.enums import LocationKind, Role, str_enum


class ShopSettings(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    """One row per tenant. Values that differ between shops or change over time live here,
    not in code (see docs/SPEC.md, Business rules)."""

    __tablename__ = "shop_settings"
    __table_args__ = (UniqueConstraint("tenant_id"),)

    id: Mapped[IntPK]
    legal_name: Mapped[str] = mapped_column(String(200))
    trade_name: Mapped[str | None] = mapped_column(String(200))
    gstin: Mapped[str | None] = mapped_column(String(15))
    state_code: Mapped[str] = mapped_column(String(2))
    address: Mapped[str] = mapped_column(Text, default="")
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(200))
    bank_name: Mapped[str | None] = mapped_column(String(100))
    bank_account_no: Mapped[str | None] = mapped_column(String(30))
    bank_ifsc: Mapped[str | None] = mapped_column(String(11))
    invoice_terms: Mapped[str | None] = mapped_column(Text)

    financial_year_start_month: Mapped[int] = mapped_column(Integer, default=4)
    return_window_days: Mapped[int] = mapped_column(Integer, default=2)
    weight_variance_pct: Mapped[Percent] = mapped_column(default=Decimal("0.50"))
    default_credit_limit: Mapped[Money] = mapped_column(default=Decimal("10000.00"))
    default_credit_days: Mapped[int] = mapped_column(Integer, default=7)
    include_gst_in_cost: Mapped[bool] = mapped_column(Boolean, default=False)
    rates_include_gst: Mapped[bool] = mapped_column(Boolean, default=False)
    cash_receipt_limit: Mapped[Money] = mapped_column(default=Decimal("200000.00"))
    eway_threshold_interstate: Mapped[Money] = mapped_column(default=Decimal("50000.00"))
    eway_threshold_intrastate: Mapped[Money] = mapped_column(default=Decimal("100000.00"))
    einvoice_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # G28: counter staff may key in supplier bills for their own shop but never see costs.
    counter_can_enter_purchases: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    # FM1: a counter user's cash-book voucher above this needs the owner's PIN.
    expense_approval_limit: Mapped[Money] = mapped_column(
        default=Decimal("5000.00"), server_default="5000.00"
    )
    # FM2: a counter user's stock adjustment worth more than this needs the owner's PIN.
    adjustment_approval_limit: Mapped[Money] = mapped_column(
        default=Decimal("10000.00"), server_default="10000.00"
    )
    # FM2 (accountant to confirm): also list unexplained shortages (count, weighbridge) as
    # ITC to reverse. Losses, theft, damage and free samples are always listed.
    itc_reverse_shortages: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    # FM5 (accountant to confirm): the share of unpaid bills to set aside as a provision for
    # doubtful debts, by how long past the due date they are. Conservative defaults.
    provision_pct_current: Mapped[Percent] = mapped_column(default=Decimal("0"), server_default="0")
    provision_pct_1_15: Mapped[Percent] = mapped_column(default=Decimal("1"), server_default="1")
    provision_pct_16_30: Mapped[Percent] = mapped_column(default=Decimal("2"), server_default="2")
    provision_pct_31_60: Mapped[Percent] = mapped_column(default=Decimal("10"), server_default="10")
    provision_pct_over_60: Mapped[Percent] = mapped_column(
        default=Decimal("50"), server_default="50"
    )
    # FM6: replenishment defaults, and how stock is valued below cost (accountant to confirm AS 2).
    default_lead_time_days: Mapped[int] = mapped_column(Integer, default=7, server_default="7")
    default_safety_days: Mapped[int] = mapped_column(Integer, default=2, server_default="2")
    fsn_fast_min_days: Mapped[int] = mapped_column(Integer, default=15, server_default="15")
    nrv_selling_cost_pct: Mapped[Percent] = mapped_column(default=Decimal("0"), server_default="0")
    nrv_writedown_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    # FM7: nothing may be dated on or before this day (F18). Set and reopened only through
    # /period-lock, with a reason, so the settings form never carries it.
    locked_through: Mapped[date | None] = mapped_column(Date)
    # FM7: how far apart in days a bank line and a receipt may be and still match.
    bank_match_days: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    # FM7: thresholds for the owner's exception report. Zero switches a rule off.
    exception_round_amount: Mapped[Money] = mapped_column(
        default=Decimal("1000.00"), server_default="1000.00"
    )
    exception_count_days: Mapped[int] = mapped_column(Integer, default=2, server_default="2")
    exception_returns_count: Mapped[int] = mapped_column(Integer, default=4, server_default="4")
    exception_returns_days: Mapped[int] = mapped_column(Integer, default=30, server_default="30")
    exception_cash_near_pct: Mapped[Percent] = mapped_column(
        default=Decimal("80"), server_default="80"
    )
    exception_shortage_count: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    # FM10: how far a supplier bill may go past the goods received (or ordered), and above the
    # order rate, before the owner must approve it. Tight by default; zero means exactly.
    po_qty_tolerance_pct: Mapped[Percent] = mapped_column(
        default=Decimal("1.00"), server_default="1.00"
    )
    po_rate_tolerance_pct: Mapped[Percent] = mapped_column(
        default=Decimal("0.50"), server_default="0.50"
    )

    __audit_exclude__ = frozenset({"updated_at"})


class Location(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    __tablename__ = "location"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code"),
        # The code prefixes document numbers, which GST caps at 16 characters:
        # code (2) + series suffix (2) + "/26-27/" (7) + sequence (5) = 16.
        CheckConstraint("code ~ '^[A-Z0-9]{1,2}$'", name="code_format"),
    )

    id: Mapped[IntPK]
    code: Mapped[str] = mapped_column(String(2))
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[LocationKind] = mapped_column(str_enum(LocationKind, "location_kind"))
    address: Mapped[str] = mapped_column(Text, default="")
    state_code: Mapped[str] = mapped_column(String(2))
    phone: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __audit_exclude__ = frozenset({"updated_at"})


class AppUser(Base, TenantMixin, TimestampMixin, ActorMixin, Audited):
    __tablename__ = "app_user"
    __table_args__ = (UniqueConstraint("tenant_id", "username"),)

    id: Mapped[IntPK]
    username: Mapped[str] = mapped_column(String(50))
    full_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[Role] = mapped_column(str_enum(Role, "role"))
    password_hash: Mapped[str] = mapped_column(String(255))
    # The owner approves counter requests by typing this PIN (G18). Hashed like a password.
    pin_hash: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    locations: Mapped[list[Location]] = relationship(
        secondary="user_location", lazy="selectin", order_by="Location.code"
    )

    __audit_exclude__ = frozenset(
        {"updated_at", "failed_login_count", "locked_until", "last_login_at"}
    )
    __audit_redact__ = frozenset({"password_hash", "pin_hash"})


class UserLocation(Base, TenantMixin):
    """Which shops or godowns a user works at. Owners and accountants see every location."""

    __tablename__ = "user_location"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), primary_key=True
    )
    location_id: Mapped[int] = mapped_column(
        ForeignKey("location.id", ondelete="RESTRICT"), primary_key=True
    )


__all__ = ["AppUser", "Location", "ShopSettings", "UserLocation"]
