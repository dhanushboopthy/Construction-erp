from datetime import datetime

from pydantic import Field

from app.core.security import MIN_PASSWORD_LENGTH
from app.models.enums import Role
from app.schemas.common import Schema
from app.schemas.location import LocationOut

Username = Field(pattern=r"^[a-z0-9_.-]{3,50}$", description="lowercase, 3-50 characters")


class UserCreate(Schema):
    username: str = Username
    full_name: str = Field(min_length=1, max_length=100)
    role: Role
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)
    location_ids: list[int] = Field(default_factory=list)


class UserUpdate(Schema):
    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    role: Role | None = None
    is_active: bool | None = None
    location_ids: list[int] | None = None


class PasswordReset(Schema):
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)


class UserOut(Schema):
    id: int
    username: str
    full_name: str
    role: Role
    is_active: bool
    last_login_at: datetime | None
    locations: list[LocationOut]
