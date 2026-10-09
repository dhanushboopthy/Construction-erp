"""Weighbridge slips and delivery proof kept against purchases, bills and trips (B17).

Files are stored under a key we make (never the uploaded name), their type is decided from the
bytes, and they are never deleted. Counter staff reach only their own shop's documents; trips
are the owner's (and the accountant may read them)."""

import hashlib
import re
import uuid
from collections.abc import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import (
    AppError,
    BusinessRuleError,
    NotFoundError,
    PayloadTooLargeError,
    PermissionDeniedError,
)
from app.core.tenancy import TENANT_ID
from app.models.documents import Attachment
from app.models.enums import AttachmentKind, AttachmentRef, Role
from app.models.purchasing import Purchase
from app.models.sales import SalesInvoice
from app.models.transport import Trip
from app.schemas.documents import AttachmentOut
from app.services.storage import StorageError, get_storage

MAX_PER_DOCUMENT = 20


def sniff(data: bytes) -> str | None:
    """The real type of the file, from its first bytes."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


EXTENSION = {
    "application/pdf": "pdf",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}


def safe_name(name: str) -> str:
    """A file name safe to show and to send in a header."""
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return (clean or "file")[:100]


def _location_of(db: Session, ref_type: AttachmentRef, ref_id: int) -> int:
    row: Purchase | SalesInvoice | Trip | None
    if ref_type is AttachmentRef.PURCHASE:
        row = db.get(Purchase, ref_id)
    elif ref_type is AttachmentRef.SALES_INVOICE:
        row = db.get(SalesInvoice, ref_id)
    else:
        row = db.get(Trip, ref_id)
    if row is None or row.tenant_id != TENANT_ID:
        raise NotFoundError("The document to attach to was not found", field="ref_id")
    return row.location_id


def _check_access(
    ref_type: AttachmentRef,
    location_id: int,
    role: Role,
    can_access: Callable[[int], bool],
    *,
    write: bool,
) -> None:
    if ref_type is AttachmentRef.TRIP and (
        role is Role.COUNTER or (write and role is not Role.OWNER)
    ):
        raise PermissionDeniedError("Trip papers are for the owner")
    if write and role is Role.ACCOUNTANT:
        raise PermissionDeniedError("The accountant can look at files but not add them")
    if not can_access(location_id):
        raise NotFoundError("The document to attach to was not found", field="ref_id")


def upload(
    db: Session,
    *,
    ref_type: AttachmentRef,
    ref_id: int,
    kind: AttachmentKind,
    file_name: str,
    data: bytes,
    note: str | None,
    actor_id: int,
    role: Role,
    can_access: Callable[[int], bool],
) -> Attachment:
    limit = get_settings().max_upload_mb * 1024 * 1024
    if len(data) > limit:
        raise PayloadTooLargeError(
            f"The file is larger than {get_settings().max_upload_mb} MB. Take a smaller photo."
        )
    if not data:
        raise BusinessRuleError("The file is empty", code="FILE_EMPTY", field="file")
    content_type = sniff(data)
    if content_type is None:
        raise AppError(
            "Only photos (JPEG, PNG, WebP) and PDF files are accepted", code="FILE_TYPE_NOT_ALLOWED"
        )
    location_id = _location_of(db, ref_type, ref_id)
    _check_access(ref_type, location_id, role, can_access, write=True)
    count = db.execute(
        select(func.count())
        .select_from(Attachment)
        .where(
            Attachment.tenant_id == TENANT_ID,
            Attachment.ref_type == ref_type,
            Attachment.ref_id == ref_id,
        )
    ).scalar_one()
    if count >= MAX_PER_DOCUMENT:
        raise BusinessRuleError(
            f"A document can hold up to {MAX_PER_DOCUMENT} files", code="TOO_MANY_FILES"
        )
    key = f"attachments/{TENANT_ID}/{uuid.uuid4().hex}.{EXTENSION[content_type]}"
    try:
        get_storage().put(key, data)
    except (StorageError, OSError) as exc:
        raise AppError("The file could not be stored. Try again.", code="STORAGE_FAILED") from exc
    row = Attachment(
        tenant_id=TENANT_ID,
        ref_type=ref_type,
        ref_id=ref_id,
        kind=kind,
        file_name=safe_name(file_name),
        content_type=content_type,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        storage_key=key,
        location_id=location_id,
        note=note,
        created_by=actor_id,
    )
    db.add(row)
    db.commit()
    return row


def list_for(
    db: Session,
    ref_type: AttachmentRef,
    ref_id: int,
    role: Role,
    can_access: Callable[[int], bool],
) -> list[AttachmentOut]:
    location_id = _location_of(db, ref_type, ref_id)
    _check_access(ref_type, location_id, role, can_access, write=False)
    rows = db.execute(
        select(Attachment)
        .where(
            Attachment.tenant_id == TENANT_ID,
            Attachment.ref_type == ref_type,
            Attachment.ref_id == ref_id,
        )
        .order_by(Attachment.id)
    ).scalars()
    return [AttachmentOut.model_validate(r) for r in rows]


def read(
    db: Session, attachment_id: int, role: Role, can_access: Callable[[int], bool]
) -> tuple[Attachment, bytes]:
    row = db.get(Attachment, attachment_id)
    if row is None or row.tenant_id != TENANT_ID:
        raise NotFoundError("File not found")
    _check_access(
        row.ref_type, _location_of(db, row.ref_type, row.ref_id), role, can_access, write=False
    )
    try:
        data = get_storage().get(row.storage_key)
    except StorageError as exc:
        raise NotFoundError("The stored file is missing. Ask for a new copy.") from exc
    if hashlib.sha256(data).hexdigest() != row.sha256:
        raise AppError("The stored file does not match its record", code="FILE_CORRUPT")
    return row, data
