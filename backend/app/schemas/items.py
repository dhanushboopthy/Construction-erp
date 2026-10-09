from decimal import Decimal
from typing import Annotated

from pydantic import Field, field_validator, model_validator

from app.models.enums import ItemCategory
from app.schemas.common import Schema

Hsn = Annotated[str, Field(pattern=r"^[0-9]{4,8}$", description="4-8 digit HSN code (G16)")]
Rate = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]
Factor = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=6)]


class ItemUnitIn(Schema):
    unit: str = Field(min_length=1, max_length=16)
    factor_to_base: Factor
    whole_only: bool = False

    @field_validator("unit")
    @classmethod
    def _lower(cls, value: str) -> str:
        return value.lower()


class ItemUnitOut(ItemUnitIn):
    id: int


class ItemBase(Schema):
    name: str = Field(min_length=1, max_length=150)
    category: ItemCategory
    brand: str | None = Field(default=None, max_length=80)
    hsn: Hsn
    gst_rate: Rate
    base_unit: str = Field(min_length=1, max_length=16)
    base_whole_only: bool = False
    size: str | None = Field(default=None, max_length=50)
    grade: str | None = Field(default=None, max_length=50)
    weight_per_piece_kg: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)] | None = (
        None
    )

    @field_validator("base_unit")
    @classmethod
    def _lower_base(cls, value: str) -> str:
        return value.lower()


def _check_units(base_unit: str, units: list[ItemUnitIn]) -> None:
    names = [u.unit for u in units]
    if len(set(names)) != len(names):
        raise ValueError("A unit is listed twice")
    if base_unit in names:
        raise ValueError("The base unit is implicit (factor 1); do not list it again")


class ItemCreate(ItemBase):
    min_margin: Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=4)] = Decimal("0")
    units: list[ItemUnitIn] = Field(default_factory=list)
    is_active: bool = True

    @model_validator(mode="after")
    def _units_ok(self) -> "ItemCreate":
        _check_units(self.base_unit, self.units)
        return self


class ItemUpdate(Schema):
    """Partial update. The base unit is fixed once stock or bills exist, so it is not editable."""

    name: str | None = Field(default=None, min_length=1, max_length=150)
    category: ItemCategory | None = None
    brand: str | None = Field(default=None, max_length=80)
    hsn: Hsn | None = None
    gst_rate: Rate | None = None
    size: str | None = Field(default=None, max_length=50)
    grade: str | None = Field(default=None, max_length=50)
    weight_per_piece_kg: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)] | None = (
        None
    )
    min_margin: Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=4)] | None = None
    units: list[ItemUnitIn] | None = None
    is_active: bool | None = None


class ItemOut(ItemBase):
    """What counter staff and the accountant see: no margin figures (rule B4)."""

    id: int
    is_active: bool
    units: list[ItemUnitOut]


class ItemOwnerOut(ItemOut):
    min_margin: Decimal


class ConversionOut(Schema):
    quantity: Decimal
    from_unit: str
    to_unit: str
    result: Decimal


class ImportRowError(Schema):
    row: int
    field: str | None
    message: str


class ImportResult(Schema):
    dry_run: bool
    created: int
    updated: int
    errors: list[ImportRowError]
