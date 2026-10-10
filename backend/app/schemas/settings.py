from datetime import date
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
    adjustment_approval_limit: Decimal = Field(default=Decimal("10000"), ge=0)
    itc_reverse_shortages: bool = True
    provision_pct_current: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    provision_pct_1_15: Decimal = Field(default=Decimal("1"), ge=0, le=100)
    provision_pct_16_30: Decimal = Field(default=Decimal("2"), ge=0, le=100)
    provision_pct_31_60: Decimal = Field(default=Decimal("10"), ge=0, le=100)
    provision_pct_over_60: Decimal = Field(default=Decimal("50"), ge=0, le=100)
    default_lead_time_days: int = Field(default=7, ge=0, le=365)
    default_safety_days: int = Field(default=2, ge=0, le=365)
    fsn_fast_min_days: int = Field(default=15, ge=1, le=90)
    nrv_selling_cost_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    nrv_writedown_enabled: bool = True
    bank_match_days: int = Field(default=3, ge=0, le=30)
    exception_round_amount: Decimal = Field(default=Decimal("1000"), ge=0)
    exception_count_days: int = Field(default=2, ge=0, le=30)
    exception_returns_count: int = Field(default=4, ge=0, le=100)
    exception_returns_days: int = Field(default=30, ge=1, le=365)
    exception_cash_near_pct: Decimal = Field(default=Decimal("80"), ge=0, le=100)
    exception_shortage_count: int = Field(default=3, ge=0, le=100)
    po_qty_tolerance_pct: Decimal = Field(default=Decimal("1"), ge=0, le=100)
    po_rate_tolerance_pct: Decimal = Field(default=Decimal("0.5"), ge=0, le=100)

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
    locked_through: date | None = None  # read-only here: change it at /period-lock


class ShopSettingsUpdate(ShopSettingsBase):
    """Full replacement of the settings (PUT)."""
