"""A company's bill designs (Milestone 28, ADR 0013). A Super Admin uploads, activates,
deactivates and deletes; Support reads and previews. Uploaded HTML is data with a placeholder
grammar, never a Jinja template, so nothing in it runs."""

from typing import Annotated

from fastapi import APIRouter, File, Form, Response, UploadFile, status

from app.api.deps import DbSession, PlatformAdminUser, SuperAdminOnly
from app.domain.bill_template import MAX_ASSET_BYTES, MAX_HTML_BYTES
from app.schemas.bill_templates import (
    Diagnostics,
    RegistryOut,
    TemplateList,
    TemplateOut,
    UploadOut,
)
from app.services.platform import bill_templates as service

router = APIRouter(prefix="/tenants/{tenant_id}/bill-templates", tags=["admin"])


@router.get("/field-registry", response_model=RegistryOut)
def field_registry(tenant_id: int, _: PlatformAdminUser, db: DbSession) -> RegistryOut:
    """Every placeholder a design may use, with a description and a sample, and what each kind
    of document may not leave out."""
    return service.registry(db, tenant_id)


@router.get("", response_model=TemplateList)
def list_templates(tenant_id: int, _: PlatformAdminUser, db: DbSession) -> TemplateList:
    """The company's designs, newest version first within each slot, and its second logo."""
    return service.list_templates(db, tenant_id)


@router.post("", response_model=UploadOut, status_code=status.HTTP_201_CREATED)
def upload_template(
    tenant_id: int,
    admin: SuperAdminOnly,
    db: DbSession,
    slot: Annotated[str, Form()],
    name: Annotated[str, Form()],
    html: Annotated[UploadFile, File()],
    images: Annotated[list[UploadFile] | None, File()] = None,
) -> UploadOut:
    """The next version of the slot's design, not yet active. The HTML is cleaned (what the
    answer's `removed` lists is gone) and refused when it leaves out a field the GST rules
    require (422 TEMPLATE_MISSING_FIELDS), or when it is too large (HTML 500 KB, 2 MB an image,
    20 images)."""
    return service.upload(
        db,
        tenant_id,
        slot=slot,
        name=name,
        html_bytes=html.file.read(MAX_HTML_BYTES + 1),
        images=[
            (image.filename or "", image.file.read(MAX_ASSET_BYTES + 1)) for image in images or []
        ],
        admin_id=admin.admin_id,
    )


@router.put("/secondary-logo", response_model=TemplateList)
def put_secondary_logo(
    tenant_id: int, admin: SuperAdminOnly, db: DbSession, file: Annotated[UploadFile, File()]
) -> TemplateList:
    """The company's second logo (PNG or JPEG, up to 2 MB). Designs no issued document uses
    follow it; the others keep the logo they were issued with."""
    return service.set_secondary_logo(
        db, tenant_id, file.file.read(MAX_ASSET_BYTES + 1), admin.admin_id
    )


@router.delete("/secondary-logo", response_model=TemplateList)
def delete_secondary_logo(tenant_id: int, admin: SuperAdminOnly, db: DbSession) -> TemplateList:
    return service.remove_secondary_logo(db, tenant_id, admin.admin_id)


@router.get("/{template_id}", response_model=TemplateOut)
def get_template(
    tenant_id: int, template_id: int, _: PlatformAdminUser, db: DbSession
) -> TemplateOut:
    return service.get_template(db, tenant_id, template_id)


@router.get("/{template_id}/diagnostics", response_model=Diagnostics)
def get_diagnostics(
    tenant_id: int, template_id: int, _: PlatformAdminUser, db: DbSession
) -> Diagnostics:
    """What will print blank, what the upload lost, the page size and the images used."""
    return service.diagnostics(db, tenant_id, template_id)


@router.post("/{template_id}/preview", response_class=Response)
def preview_template(
    tenant_id: int, template_id: int, _: PlatformAdminUser, db: DbSession
) -> Response:
    """A PDF of the design with sample figures, drawn by the renderer real bills use. A read, so
    Support may ask for it."""
    pdf, filename = service.preview(db, tenant_id, template_id)
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post("/{template_id}/activate", response_model=TemplateOut)
def activate(tenant_id: int, template_id: int, admin: SuperAdminOnly, db: DbSession) -> TemplateOut:
    """New documents of this slot use this design; the slot's previous design is stood down.
    Documents already issued keep the design they were issued with."""
    return service.set_active(db, tenant_id, template_id, True, admin.admin_id)


@router.post("/{template_id}/deactivate", response_model=TemplateOut)
def deactivate(
    tenant_id: int, template_id: int, admin: SuperAdminOnly, db: DbSession
) -> TemplateOut:
    """New documents of this slot go back to the built-in layout."""
    return service.set_active(db, tenant_id, template_id, False, admin.admin_id)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    tenant_id: int, template_id: int, admin: SuperAdminOnly, db: DbSession
) -> Response:
    """409 TEMPLATE_IN_USE when an issued document points at it, 409 TEMPLATE_ACTIVE when it
    is active."""
    service.delete(db, tenant_id, template_id, admin.admin_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
