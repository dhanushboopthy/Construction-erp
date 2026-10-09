from typing import Annotated

from fastapi import APIRouter, File, Form, Response, UploadFile, status

from app.api.deps import CurrentPrincipal, DbSession
from app.core.config import get_settings
from app.models.enums import AttachmentKind, AttachmentRef
from app.schemas.documents import AttachmentOut
from app.services import attachments as service

router = APIRouter(prefix="/attachments", tags=["attachments"])


@router.post("", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED)
def upload_file(
    principal: CurrentPrincipal,
    db: DbSession,
    ref_type: Annotated[AttachmentRef, Form()],
    ref_id: Annotated[int, Form()],
    kind: Annotated[AttachmentKind, Form()],
    file: Annotated[UploadFile, File()],
    note: Annotated[str | None, Form(max_length=200)] = None,
) -> AttachmentOut:
    """Attach a weighbridge slip or delivery proof (photo or PDF, up to the size limit)."""
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)  # one byte more than allowed, so a big file is noticed
    row = service.upload(
        db,
        ref_type=ref_type,
        ref_id=ref_id,
        kind=kind,
        file_name=file.filename or "file",
        data=data,
        note=note or None,
        actor_id=principal.user_id,
        role=principal.role,
        can_access=principal.can_access_location,
    )
    return AttachmentOut.model_validate(row)


@router.get("", response_model=list[AttachmentOut])
def list_files(
    principal: CurrentPrincipal, db: DbSession, ref_type: AttachmentRef, ref_id: int
) -> list[AttachmentOut]:
    return service.list_for(db, ref_type, ref_id, principal.role, principal.can_access_location)


@router.get("/{attachment_id}/file", response_class=Response)
def download(attachment_id: int, principal: CurrentPrincipal, db: DbSession) -> Response:
    row, data = service.read(db, attachment_id, principal.role, principal.can_access_location)
    return Response(
        data,
        media_type=row.content_type,
        headers={
            "Content-Disposition": f'inline; filename="{row.file_name}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
