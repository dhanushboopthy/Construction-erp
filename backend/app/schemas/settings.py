from decimal import Decimal

from pydantic import Field, ValidationInfo, field_validator

from app.schemas.common import Gstin, Schema, StateCode


class ShopSettingsBase(Schema):
    legal_name: str = Field(min_length=1, max_length=200)
    trade_name: str | None = Field(default=None, max_length=200)
    state_code: StateCode
    gstin: Gstin = None
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
    counter_can_enter_purchases: bool = True
    timezone: str = "Asia/Kolkata"
    expense_approval_limit: Decimal = Field(default=Decimal("5000"), ge=0)

    @field_validator("gstin")
    @classmethod
    def _gstin_matches_state(cls, value: str | None, info: ValidationInfo) -> str | None:
        # The first two digits of a GSTIN are the state it was issued in.
        state = info.data.get("state_code")
        if value and state and value[:2] != state:
            raise ValueError("The first two digits of the GSTIN must match the state code")
        return value


class ShopSettingsOut(ShopSettingsBase):
    id: int


class ShopSettingsUpdate(ShopSettingsBase):
    """Full replacement of the settings (PUT)."""
