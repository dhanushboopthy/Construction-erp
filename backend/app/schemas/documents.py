from datetime import datetime

from pydantic import Field

from app.models.enums import AttachmentKind, AttachmentRef
from app.schemas.common import Schema


class AttachmentOut(Schema):
    id: int
    ref_type: AttachmentRef
    ref_id: int
    kind: AttachmentKind
    file_name: str
    content_type: str
    size_bytes: int
    note: str | None
    created_at: datetime
    created_by: int | None


class AttachmentNote(Schema):
    note: str | None = Field(default=None, max_length=200)
