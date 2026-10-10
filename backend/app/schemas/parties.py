from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import Field, model_validator

from app.models.enums import CustomerSegment, PartyType
from app.schemas.common import Gstin, Schema, StateCode


class SiteBase(Schema):
    name: str = Field(min_length=1, max_length=150)
    address: str = ""
    state_code: StateCode
    gstin: Gstin = None  # blank prints as "URP" on e-way bills (G13)


class SiteCreate(SiteBase):
    @model_validator(mode="after")
    def _gstin_state(self) -> "SiteCreate":
        if self.gstin and self.gstin[:2] != self.state_code:
            raise ValueError("The first two digits of the GSTIN must match the state code")
        return self


class SiteUpdate(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    address: str | None = None
    state_code: StateCode | None = None
    gstin: Gstin = None
    is_active: bool | None = None


class SiteOut(SiteBase):
    id: int
    party_id: int
    is_active: bool


class PartyBase(Schema):
    name: str = Field(min_length=1, max_length=150)
    type: PartyType
    segment: CustomerSegment | None = None
    gstin: Gstin = None
    state_code: StateCode
    address: str = ""
    phone: str | None = Field(default=None, max_length=20)


class PartyCreate(PartyBase):
    # Credit fields are owner-only (B8, rule table in SPEC section 2).
    credit_allowed: bool = False
    credit_limit: Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)] | None = None
    credit_days: Annotated[int, Field(ge=0, le=365)] | None = None
    sites: list[SiteCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> "PartyCreate":
        if self.gstin and self.gstin[:2] != self.state_code:
            raise ValueError("The first two digits of the GSTIN must match the state code")
        if self.segment and self.type is PartyType.SUPPLIER:
            raise ValueError("A segment applies to customers only")
        return self


class PartyUpdate(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    type: PartyType | None = None
    segment: CustomerSegment | None = None
    gstin: Gstin = None
    state_code: StateCode | None = None
    address: str | None = None
    phone: str | None = Field(default=None, max_length=20)
    credit_allowed: bool | None = None
    credit_limit: Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)] | None = None
    credit_days: Annotated[int, Field(ge=0, le=365)] | None = None
    lead_time_days: Annotated[int, Field(ge=0, le=365)] | None = None
    is_active: bool | None = None


class PartyOut(PartyBase):
    id: int
    credit_allowed: bool
    credit_limit: Decimal | None
    credit_days: int | None
    lead_time_days: int | None
    is_active: bool
    created_at: datetime
    sites: list[SiteOut]
