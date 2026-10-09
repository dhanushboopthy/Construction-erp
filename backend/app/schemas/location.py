from datetime import datetime

from pydantic import Field

from app.models.enums import LocationKind
from app.schemas.common import Schema, StateCode


class LocationBase(Schema):
    name: str = Field(min_length=1, max_length=100)
    kind: LocationKind
    address: str = ""
    state_code: StateCode
    phone: str | None = Field(default=None, max_length=20)


class LocationCreate(LocationBase):
    code: str = Field(
        pattern=r"^[A-Z0-9]{1,2}$",
        description="1-2 uppercase letters/digits, prefixes document numbers (e.g. S1, G1)",
    )


class LocationUpdate(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    address: str | None = None
    state_code: StateCode | None = None
    phone: str | None = Field(default=None, max_length=20)
    is_active: bool | None = None


class LocationOut(LocationBase):
    id: int
    code: str
    is_active: bool
    created_at: datetime
