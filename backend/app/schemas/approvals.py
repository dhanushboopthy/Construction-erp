from datetime import datetime

from pydantic import Field

from app.models.enums import ApprovalAction
from app.schemas.common import Schema


class ApprovalRequest(Schema):
    pin: str = Field(min_length=4, max_length=12, pattern=r"^[0-9]+$")
    action: ApprovalAction
    reason: str = Field(min_length=3, max_length=300)
    party_id: int | None = None


class ApprovalOut(Schema):
    id: int
    action: ApprovalAction
    expires_at: datetime
    approved_by_name: str


class PinSet(Schema):
    current_password: str = Field(min_length=1, max_length=128)
    pin: str = Field(min_length=4, max_length=12, pattern=r"^[0-9]+$")
