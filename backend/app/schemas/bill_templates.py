"""Bill designs, as Duolink's admin sees them (Milestone 28). Counts, names and sample text only:
no figure of the company's own appears in any of these (ADR 0012)."""

from datetime import datetime

from app.models.enums import BillSlot
from app.schemas.common import Schema


class FieldOut(Schema):
    key: str
    group: str
    description: str
    sample: str
    slots: list[BillSlot]
    image: bool


class RequirementOut(Schema):
    label: str


class LimitsOut(Schema):
    html_bytes: int
    image_bytes: int
    images: int


class RegistryOut(Schema):
    fields: list[FieldOut]
    formats: list[str]
    slots: list[BillSlot]
    required: dict[str, list[str]]  # per slot: what a design may not leave out
    limits: LimitsOut


class TemplateOut(Schema):
    id: int
    slot: BillSlot
    name: str
    version: int
    is_active: bool
    used: bool  # an issued document points at it: it can no longer be deleted
    html_bytes: int
    images: list[str]
    removed: list[str]  # what cleaning took out of the upload
    uploaded_by_name: str | None
    created_at: datetime
    activated_at: datetime | None


class SecondaryLogoOut(Schema):
    content_type: str
    sha256: str


class TemplateList(Schema):
    templates: list[TemplateOut]
    secondary_logo: SecondaryLogoOut | None


class Diagnostics(Schema):
    unknown: list[str]  # not a field: prints blank
    other_slot: list[str]  # a field this document does not have: prints blank
    outside_rows: list[str]  # a line or HSN field outside its repeating row: prints blank
    in_styles: list[str]  # inside a style: never filled
    item_rows: int
    hsn_rows: int
    images: list[str]  # images and company logos the design shows
    missing_images: list[str]  # images the upload referred to but did not include
    unused_images: list[str]  # uploaded but never shown
    page_size: str | None
    removed: list[str]
    missing_fields: list[str]  # what a tax document may not leave out (none, once stored)
    warnings: list[str]


class UploadOut(TemplateOut):
    diagnostics: Diagnostics
