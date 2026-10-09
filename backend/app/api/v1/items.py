from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, File, Query, Response, UploadFile, status

from app.api.deps import CurrentPrincipal, DbSession, OwnerOnly, Principal
from app.core.errors import BusinessRuleError
from app.models.enums import ItemCategory
from app.models.masters import Item
from app.schemas.common import Page
from app.schemas.items import (
    ConversionOut,
    ImportResult,
    ItemCreate,
    ItemOut,
    ItemOwnerOut,
    ItemUpdate,
)
from app.services import item_import
from app.services import items as item_service

router = APIRouter(prefix="/items", tags=["items"])

MAX_UPLOAD_BYTES = 2_000_000
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def shape(principal: Principal, item: Item) -> ItemOut | ItemOwnerOut:
    """Margin figures only reach the owner: separate response models (rule B4)."""
    model = ItemOwnerOut if principal.sees_cost else ItemOut
    return model.model_validate(item)


@router.get("", response_model=Page[ItemOwnerOut] | Page[ItemOut])
def list_items(
    principal: CurrentPrincipal,
    db: DbSession,
    q: str | None = None,
    category: ItemCategory | None = None,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ItemOwnerOut] | Page[ItemOut]:
    rows, total = item_service.list_items(
        db, q=q, category=category, include_inactive=include_inactive, limit=limit, offset=offset
    )
    page = Page[ItemOwnerOut] if principal.sees_cost else Page[ItemOut]
    return page(items=[shape(principal, r) for r in rows], total=total, limit=limit, offset=offset)


@router.post("", response_model=ItemOwnerOut, status_code=status.HTTP_201_CREATED)
def create_item(body: ItemCreate, _: OwnerOnly, db: DbSession) -> ItemOwnerOut:
    return ItemOwnerOut.model_validate(item_service.create_item(db, body))


@router.get("/import/template", summary="Excel template for the item import")
def import_template(_: OwnerOnly) -> Response:
    return Response(
        item_import.template_bytes(),
        media_type=XLSX,
        headers={"Content-Disposition": 'attachment; filename="items-template.xlsx"'},
    )


@router.post("/import", response_model=ImportResult)
def import_items(
    _: OwnerOnly,
    db: DbSession,
    file: Annotated[UploadFile, File()],
    dry_run: bool = True,
) -> ImportResult:
    """Check a sheet with dry_run=true, then send it again with dry_run=false to save."""
    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise BusinessRuleError("The file is larger than 2 MB", code="FILE_TOO_LARGE")
    return item_import.import_items(db, content, dry_run=dry_run)


@router.get("/{item_id}", response_model=ItemOwnerOut | ItemOut)
def get_item(item_id: int, principal: CurrentPrincipal, db: DbSession) -> ItemOwnerOut | ItemOut:
    return shape(principal, item_service.get_item(db, item_id))


@router.patch("/{item_id}", response_model=ItemOwnerOut)
def update_item(item_id: int, body: ItemUpdate, _: OwnerOnly, db: DbSession) -> ItemOwnerOut:
    return ItemOwnerOut.model_validate(item_service.update_item(db, item_id, body))


@router.get("/{item_id}/convert", response_model=ConversionOut)
def convert_item_quantity(
    item_id: int,
    _: CurrentPrincipal,
    db: DbSession,
    quantity: Annotated[Decimal, Query(ge=0)],
    from_unit: str,
    to_unit: str,
) -> ConversionOut:
    result = item_service.convert_quantity(db, item_id, quantity, from_unit, to_unit)
    return ConversionOut(
        quantity=quantity, from_unit=from_unit.lower(), to_unit=to_unit.lower(), result=result
    )
