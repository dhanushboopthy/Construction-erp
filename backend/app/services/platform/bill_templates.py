"""Duolink gives a company its own bill design (Milestone 28, ADR 0013).

An upload is cleaned (what a browser would run is removed, and the company is told what), checked
against the fields the GST rules require of that kind of document, and stored as the next version
of its slot. A version is never edited. Only a design that no issued document points at can be
deleted. All of it is written to the platform audit log; no figure of the company's own is read
or answered.
"""

import hashlib
import re
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, BusinessRuleError, ConflictError, NotFoundError
from app.core.tenancy import current_tenant_id, tenant_context
from app.domain import bill_html
from app.domain import bill_template as rules
from app.models.bill_templates import BillTemplate, BillTemplateAsset
from app.models.enums import BillSlot, PlatformAction
from app.models.platform import PlatformAdmin
from app.schemas.bill_templates import (
    Diagnostics,
    FieldOut,
    LimitsOut,
    RegistryOut,
    SecondaryLogoOut,
    TemplateList,
    TemplateOut,
    UploadOut,
)
from app.services import bill_render, shop_settings
from app.services import bill_templates as company_side
from app.services.platform.audit import record
from app.services.platform.tenants import get_tenant
from app.services.storage import StorageError, get_storage


def _refuse(exc: rules.TemplateRuleError) -> BusinessRuleError:
    return BusinessRuleError(str(exc), code=exc.code)


def _key(tenant_id: int, kind: str, digest: str, extension: str = "") -> str:
    return f"bill-template/{tenant_id}/{kind}/{digest[:32]}{extension}"


def _put(key: str, data: bytes) -> None:
    try:
        get_storage().put(key, data)
    except (StorageError, OSError) as exc:
        raise AppError("The file could not be stored. Try again.", code="STORAGE_FAILED") from exc


def registry(db: Session, tenant_id: int) -> RegistryOut:
    get_tenant(db, tenant_id)  # 404 for a company that does not exist
    return RegistryOut(
        fields=[
            FieldOut(
                key=f.key,
                group=f.group,
                description=f.description,
                sample=f.sample,
                slots=[BillSlot(s) for s in f.slots],
                image=f.image,
            )
            for f in rules.FIELDS
        ],
        formats=list(rules.FORMATS),
        slots=[BillSlot(s) for s in rules.SLOTS],
        required={s: [r.label for r in rules.requirements(s)] for s in rules.SLOTS},
        limits=LimitsOut(
            html_bytes=rules.MAX_HTML_BYTES,
            image_bytes=rules.MAX_ASSET_BYTES,
            images=rules.MAX_ASSETS,
        ),
    )


def _get(db: Session, template_id: int) -> BillTemplate:
    row = db.scalar(
        select(BillTemplate).where(
            BillTemplate.tenant_id == current_tenant_id(db), BillTemplate.id == template_id
        )
    )
    if row is None:
        raise NotFoundError("Bill design not found", code="TEMPLATE_NOT_FOUND")
    return row


def _views(db: Session, rows: Sequence[BillTemplate]) -> list[TemplateOut]:
    used = company_side.used_ids(db)
    names = {
        a.id: a.full_name
        for a in db.scalars(
            select(PlatformAdmin).where(
                PlatformAdmin.id.in_(
                    {r.uploaded_by_admin_id for r in rows if r.uploaded_by_admin_id}
                )
            )
        )
    }
    images: dict[int, list[str]] = {}
    for asset in db.scalars(
        select(BillTemplateAsset)
        .where(
            BillTemplateAsset.tenant_id == current_tenant_id(db),
            BillTemplateAsset.template_id.in_([r.id for r in rows]),
        )
        .order_by(BillTemplateAsset.name)
    ):
        images.setdefault(asset.template_id, []).append(asset.name)
    return [
        TemplateOut(
            id=r.id,
            slot=r.slot,
            name=r.name,
            version=r.version,
            is_active=r.is_active,
            used=r.id in used,
            html_bytes=r.html_size,
            images=images.get(r.id, []),
            removed=list(r.removed or []),
            uploaded_by_name=names.get(r.uploaded_by_admin_id or 0),
            created_at=r.created_at,
            activated_at=r.activated_at,
        )
        for r in rows
    ]


def list_templates(db: Session, tenant_id: int) -> TemplateList:
    tenant = get_tenant(db, tenant_id)
    with tenant_context(db, tenant.id):
        rows = list(
            db.scalars(
                select(BillTemplate)
                .where(BillTemplate.tenant_id == tenant.id)
                .order_by(BillTemplate.slot, BillTemplate.version.desc())
            )
        )
        row = shop_settings.get_settings_row(db)
        logo = (
            SecondaryLogoOut(content_type=row.secondary_logo_type, sha256=row.secondary_logo_sha256)
            if row.secondary_logo_key and row.secondary_logo_type and row.secondary_logo_sha256
            else None
        )
        return TemplateList(templates=_views(db, rows), secondary_logo=logo)


def get_template(db: Session, tenant_id: int, template_id: int) -> TemplateOut:
    tenant = get_tenant(db, tenant_id)
    with tenant_context(db, tenant.id):
        return _views(db, [_get(db, template_id)])[0]


def _read_html(row: BillTemplate) -> str:
    try:
        return get_storage().get(row.html_key).decode("utf-8")
    except StorageError as exc:
        raise NotFoundError("The stored design is missing", code="TEMPLATE_FILE_MISSING") from exc


def _diagnostics(db: Session, row: BillTemplate) -> Diagnostics:
    html = _read_html(row)
    report = bill_html.analyse(html, row.slot.value)
    uploaded = set(
        db.scalars(
            select(BillTemplateAsset.name).where(
                BillTemplateAsset.tenant_id == current_tenant_id(db),
                BillTemplateAsset.template_id == row.id,
            )
        )
    )
    shown = {i for i in report.images if not i.startswith(("company.", "einvoice."))}
    named = [r.split("'")[1] for r in row.removed or [] if r.startswith("image '")]
    # An image that points outside the design (a web address, a path) is not "missing".
    missing = [n for n in named if n and not re.match(r"^([A-Za-z][A-Za-z0-9+.-]*:|/|\.)", n)]
    unused = sorted(uploaded - shown)
    warnings: list[str] = []
    if report.unknown:
        warnings.append(f"{len(report.unknown)} placeholder(s) are not fields and print blank.")
    if report.other_slot:
        warnings.append("Some placeholders belong to another kind of document and print blank.")
    if report.outside_rows:
        warnings.append(
            "Some line or HSN placeholders sit outside a repeating row and print blank."
        )
    if report.in_styles:
        warnings.append("Placeholders inside a style are never filled.")
    if row.slot.value in rules.TAX_DOCUMENT_SLOTS and report.item_rows == 0:
        warnings.append("No row repeats per item: the document would print no lines.")
    if report.page_size is None:
        warnings.append("The design sets no page size; A4 is used.")
    if missing:
        warnings.append("Some images in the upload were not included, so they were removed.")
    if unused:
        warnings.append("Some uploaded images are not used by the design.")
    return Diagnostics(
        unknown=list(report.unknown),
        other_slot=list(report.other_slot),
        outside_rows=list(report.outside_rows),
        in_styles=list(report.in_styles),
        item_rows=report.item_rows,
        hsn_rows=report.hsn_rows,
        images=list(report.images),
        missing_images=missing,
        unused_images=unused,
        page_size=report.page_size,
        removed=list(row.removed or []),
        missing_fields=list(report.missing),
        warnings=warnings,
    )


def diagnostics(db: Session, tenant_id: int, template_id: int) -> Diagnostics:
    tenant = get_tenant(db, tenant_id)
    with tenant_context(db, tenant.id):
        return _diagnostics(db, _get(db, template_id))


def upload(
    db: Session,
    tenant_id: int,
    *,
    slot: str,
    name: str,
    html_bytes: bytes,
    images: Sequence[tuple[str, bytes]],
    admin_id: int,
) -> UploadOut:
    tenant = get_tenant(db, tenant_id)
    try:
        rules.check_slot(slot)
        text = rules.decode_html(html_bytes)
        rules.check_assets(images)
        cleaned = bill_html.clean(text, {n for n, _ in images})
        report = bill_html.analyse(cleaned.html, slot)
    except rules.TemplateRuleError as exc:
        raise _refuse(exc) from exc
    if report.missing:
        raise BusinessRuleError(
            "This design leaves out what a GST document must show: "
            + "; ".join(report.missing)
            + ".",
            code="TEMPLATE_MISSING_FIELDS",
            extra={"missing_fields": list(report.missing)},
        )
    if report.wording:
        raise BusinessRuleError(
            "A proforma invoice or quotation may not call itself a tax invoice.",
            code="TEMPLATE_WORDING",
        )
    if not name.strip():
        raise BusinessRuleError("Give the design a name.", code="TEMPLATE_NAME", field="name")
    body = cleaned.html.encode("utf-8")
    digest = hashlib.sha256(body).hexdigest()
    with tenant_context(db, tenant.id):
        version = (
            db.scalar(
                select(func.max(BillTemplate.version)).where(
                    BillTemplate.tenant_id == tenant.id, BillTemplate.slot == BillSlot(slot)
                )
            )
            or 0
        ) + 1
        html_key = _key(tenant.id, "html", digest, ".html")
        _put(html_key, body)
        settings_row = shop_settings.get_settings_row(db)
        row = BillTemplate(
            tenant_id=tenant.id,
            slot=BillSlot(slot),
            name=name.strip()[:120],
            version=version,
            html_key=html_key,
            html_sha256=digest,
            html_size=len(body),
            is_active=False,
            uploaded_by_admin_id=admin_id,
            removed=list(cleaned.removed),
            secondary_logo_key=settings_row.secondary_logo_key,
            secondary_logo_type=settings_row.secondary_logo_type,
            secondary_logo_sha256=settings_row.secondary_logo_sha256,
        )
        db.add(row)
        db.flush()
        for image_name, data in images:
            image_digest = hashlib.sha256(data).hexdigest()
            key = _key(tenant.id, "image", image_digest)
            _put(key, data)
            db.add(
                BillTemplateAsset(
                    tenant_id=tenant.id,
                    template_id=row.id,
                    name=image_name,
                    content_type=rules.check_asset(image_name, data),
                    key=key,
                    sha256=image_digest,
                    size_bytes=len(data),
                )
            )
        db.flush()
        record(
            db,
            PlatformAction.BILL_TEMPLATE_UPLOAD,
            admin_id,
            tenant_id=tenant.id,
            details={
                "slot": slot,
                "version": version,
                "name": row.name,
                "bytes": len(body),
                "images": len(images),
                "removed": len(cleaned.removed),
            },
        )
        db.commit()
        view = _views(db, [row])[0]
        return UploadOut(**view.model_dump(), diagnostics=_diagnostics(db, row))


def set_active(
    db: Session, tenant_id: int, template_id: int, active: bool, admin_id: int
) -> TemplateOut:
    """Activating stands down only the previous design of the same slot. Deactivating leaves the
    slot on the built-in layout for new documents; documents already issued keep their design."""
    tenant = get_tenant(db, tenant_id)
    with tenant_context(db, tenant.id):
        row = _get(db, template_id)
        if row.is_active != active:
            if active:
                previous = db.scalar(
                    select(BillTemplate).where(
                        BillTemplate.tenant_id == tenant.id,
                        BillTemplate.slot == row.slot,
                        BillTemplate.is_active.is_(True),
                    )
                )
                if previous is not None:
                    previous.is_active = False
                    db.flush()  # the one-active index needs the old one down first
                row.activated_at = datetime.now(UTC)
            row.is_active = active
            record(
                db,
                PlatformAction.BILL_TEMPLATE_ACTIVATE
                if active
                else PlatformAction.BILL_TEMPLATE_DEACTIVATE,
                admin_id,
                tenant_id=tenant.id,
                details={"slot": row.slot.value, "version": row.version},
            )
            db.commit()
        return _views(db, [row])[0]


def delete(db: Session, tenant_id: int, template_id: int, admin_id: int) -> None:
    tenant = get_tenant(db, tenant_id)
    with tenant_context(db, tenant.id):
        row = _get(db, template_id)
        if row.id in company_side.used_ids(db):
            raise ConflictError(
                "An issued document was printed with this design, so it cannot be deleted. "
                "Deactivate it instead.",
                code="TEMPLATE_IN_USE",
            )
        if row.is_active:
            raise ConflictError(
                "Deactivate this design before deleting it.", code="TEMPLATE_ACTIVE"
            )
        record(
            db,
            PlatformAction.BILL_TEMPLATE_DELETE,
            admin_id,
            tenant_id=tenant.id,
            details={"slot": row.slot.value, "version": row.version, "name": row.name},
        )
        for asset in db.scalars(
            select(BillTemplateAsset).where(BillTemplateAsset.template_id == row.id)
        ):
            db.delete(asset)
        db.flush()
        db.delete(row)
        db.commit()


def preview(db: Session, tenant_id: int, template_id: int) -> tuple[bytes, str]:
    """The design drawn with sample figures, by the renderer a real bill goes through. Reads no
    figure of the company's."""
    tenant = get_tenant(db, tenant_id)
    with tenant_context(db, tenant.id):
        row = _get(db, template_id)
        loaded = bill_render.load(db, row.id)
        if loaded is None:
            raise NotFoundError("The stored design is missing", code="TEMPLATE_FILE_MISSING")
        pdf = bill_render.preview(loaded, rules.sample_data(row.slot.value))
        return pdf, f"{row.slot.value}-v{row.version}.pdf"


def _repoint(
    db: Session, tenant_id: int, key: str | None, kind: str | None, sha: str | None
) -> int:
    """Designs no document uses follow the company's current second logo; those a document
    uses keep the one they were issued with."""
    used = company_side.used_ids(db)
    moved = 0
    for row in db.scalars(select(BillTemplate).where(BillTemplate.tenant_id == tenant_id)):
        if row.id not in used:
            row.secondary_logo_key, row.secondary_logo_type, row.secondary_logo_sha256 = (
                key,
                kind,
                sha,
            )
            moved += 1
    return moved


def set_secondary_logo(db: Session, tenant_id: int, data: bytes, admin_id: int) -> TemplateList:
    tenant = get_tenant(db, tenant_id)
    try:
        content_type = rules.check_asset("secondary-logo", data)
    except rules.TemplateRuleError as exc:
        raise _refuse(exc) from exc
    digest = hashlib.sha256(data).hexdigest()
    key = _key(tenant.id, "logo", digest)
    with tenant_context(db, tenant.id):
        _put(key, data)
        row = shop_settings.get_settings_row(db)
        row.secondary_logo_key = key
        row.secondary_logo_type = content_type
        row.secondary_logo_sha256 = digest
        moved = _repoint(db, tenant.id, key, content_type, digest)
        record(
            db,
            PlatformAction.SECONDARY_LOGO_SET,
            admin_id,
            tenant_id=tenant.id,
            details={"type": content_type, "bytes": len(data), "designs_updated": moved},
        )
        db.commit()
    return list_templates(db, tenant_id)


def remove_secondary_logo(db: Session, tenant_id: int, admin_id: int) -> TemplateList:
    tenant = get_tenant(db, tenant_id)
    with tenant_context(db, tenant.id):
        row = shop_settings.get_settings_row(db)
        row.secondary_logo_key = row.secondary_logo_type = row.secondary_logo_sha256 = None
        moved = _repoint(db, tenant.id, None, None, None)
        record(
            db,
            PlatformAction.SECONDARY_LOGO_REMOVE,
            admin_id,
            tenant_id=tenant.id,
            details={"designs_updated": moved},
        )
        db.commit()
    return list_templates(db, tenant_id)
