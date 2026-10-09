from datetime import datetime
from typing import Any

from app.models.enums import AuditAction
from app.schemas.common import Schema


class AuditLogOut(Schema):
    id: int
    at: datetime
    user_id: int | None
    action: AuditAction
    entity: str
    entity_id: str | None
    changes: dict[str, Any] | None
    request_id: str | None
    ip: str | None
