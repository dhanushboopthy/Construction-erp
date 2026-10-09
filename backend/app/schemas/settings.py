from decimal import Decimal

from pydantic import Field

from app.schemas.common import Gstin, Schema, StateCode


class ShopSettingsBase(Schema):
    legal_name: str = Field(min_length=1, max_length=200)
    trade_name: str | None = Field(default=None, max_length=200)
    gstin: Gstin = None
    state_code: StateCode
    address: str = ""
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=200)
    bank_name: str | None = Field(default=None, max_length=100)
    bank_account_no: str | None = Field(default=None, max_length=30)
    bank_ifsc: str | None = Field(default=None, pattern=r"^[A-Z]{4}0[A-Z0-9]{6}$")
    invoice_terms: str | None = None

    financial_year_start_month: int = Field(default=4, ge=1, le=12)
    return_window_days: int = Field(default=2, ge=0, le=30)
    weight_variance_pct: Decimal = Field(default=Decimal("0.50"), ge=0, le=100)
    default_credit_limit: Decimal = Field(default=Decimal("10000"), ge=0)
    default_credit_days: int = Field(default=7, ge=0, le=365)
    include_gst_in_cost: bool = False
    rates_include_gst: bool = False
    cash_receipt_limit: Decimal = Field(default=Decimal("200000"), ge=0)
    eway_threshold_interstate: Decimal = Field(default=Decimal("50000"), ge=0)
    eway_threshold_intrastate: Decimal = Field(default=Decimal("100000"), ge=0)
    einvoice_enabled: bool = False
    timezone: str = "Asia/Kolkata"


class ShopSettingsOut(ShopSettingsBase):
    id: int


class ShopSettingsUpdate(ShopSettingsBase):
    """Full replacement of the settings (PUT)."""
