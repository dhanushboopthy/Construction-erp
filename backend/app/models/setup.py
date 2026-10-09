"""Setup tables: shop settings, locations, users and their location assignments."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
