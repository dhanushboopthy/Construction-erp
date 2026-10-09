from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Self

from pydantic import Field, model_validator

from app.models.enums import OpeningKind, OpeningStatus
from app.schemas.common import Schema

Qty = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]
Cost = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=4)]
Amount = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]
MONEY_KINDS = {
    OpeningKind.RECEIVABLE,
    OpeningKind.CUSTOMER_ADVANCE,
    OpeningKind.PAYABLE,
    OpeningKind.SUPPLIER_ADVANCE,
}


class OpeningCreate(Schema):
    kind: OpeningKind
    as_of: date
    item_id: int | None = None
    location_id: int | None = None
    quantity: Qty | None = None
    unit_cost: Cost | None = None
    party_id: int | None = None
    site_id: int | None = None
    amount: Amount | None = None
    note: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _shape(self) -> Self:
        if self.kind is OpeningKind.STOCK:
            missing = [
                name
                for name in ("item_id", "location_id", "quantity", "unit_cost")
                if getattr(self, name) is None
            ]
            if missing:
                raise ValueError(f"Opening stock needs {', '.join(missing)}")
            if self.party_id or self.site_id or self.amount:
                raise ValueError("Opening stock has no party or amount")
        else:
            if self.party_id is None or self.amount is None:
                raise ValueError("A balance needs a party and an amount")
            if self.item_id or self.location_id or self.quantity or self.unit_cost:
                raise ValueError("A balance has no item, location or quantity")
        return self


class OpeningUpdate(Schema):
    as_of: date | None = None
    location_id: int | None = None
    quantity: Qty | None = None
    unit_cost: Cost | None = None
    site_id: int | None = None
    amount: Amount | None = None
    note: str | None = Field(default=None, max_length=200)


class OpeningOut(Schema):
    id: int
    kind: OpeningKind
    status: OpeningStatus
    as_of: date
    item_id: int | None
    item_name: str | None = None
    base_unit: str | None = None
    location_id: int | None
    location_code: str | None = None
    quantity: Decimal | None
    unit_cost: Decimal | None
    party_id: int | None
    party_name: str | None = None
    site_id: int | None
    site_name: str | None = None
    amount: Decimal | None
    note: str | None
    posted_at: datetime | None


class PostRequest(Schema):
    kinds: list[OpeningKind] = Field(min_length=1)


class PostResult(Schema):
    posted: int
    stock_rows: int
    party_rows: int
