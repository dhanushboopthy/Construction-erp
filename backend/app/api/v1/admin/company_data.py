"""A company's data and number series (Milestone 26, ADR 0013). Super Admin only, reads
included: Support gets 403 on every route here. The company is read from the `tenant` table
before anything else, so an id in the URL is not authority over that company."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession, SuperAdminOnly
from app.schemas.platform_data import (
    DataInventory,
    DataPreviewOut,
    DataViewOut,
    DeleteAllIn,
    DeleteOut,
    DeleteSelectedIn,
    NumberingOut,
    NumberingRow,
    NumberingSetIn,
)
from app.services.platform import data_management as data
from app.services.platform import numbering as numbering

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["admin"])


@router.get("/data", response_model=DataInventory)
def inventory(tenant_id: int, _: SuperAdminOnly, db: DbSession) -> DataInventory:
    """Every kind of business data with its row count and what blocks its deletion (the real
    foreign-key graph, for example "Parties: blocked by 120 Sales bills")."""
    return data.inventory(db, tenant_id)


@router.get("/data/preview", response_model=DataPreviewOut)
def preview(
    tenant_id: int,
    _: SuperAdminOnly,
    db: DbSession,
    keys: Annotated[list[str] | None, Query(description="kinds, or 'all'")] = None,
) -> DataPreviewOut:
    """What a deletion of these kinds (default `all`) would remove, per table, with the files
    and the blockers. Fetched when a dialog opens. 422 UNKNOWN_DATA_KIND."""
    return data.preview(db, tenant_id, keys or "all")


@router.get("/data/{key}", response_model=DataViewOut)
def view(tenant_id: int, key: str, _: SuperAdminOnly, db: DbSession) -> DataViewOut:
    """The latest 25 rows of one kind as four identifying columns (never an amount).
    422 UNKNOWN_DATA_KIND."""
    return data.view(db, tenant_id, key)


@router.post("/data/delete", response_model=DeleteOut)
def delete_selected(
    tenant_id: int, body: DeleteSelectedIn, admin: SuperAdminOnly, db: DbSession
) -> DeleteOut:
    """Delete the chosen kinds. `confirm` must be `DELETE`. A protected safety backup is taken
    first. 409 DATA_BLOCKED (a kind that is not chosen still points at one that is),
    SAFETY_BACKUP_FAILED; 422 CONFIRMATION_MISMATCH, UNKNOWN_DATA_KIND; 500 DATA_DELETE_FAILED
    (nothing was removed). Audited."""
    return data.delete_selected(db, tenant_id, body.keys, body.confirm, admin.admin_id)


@router.post("/data/delete-all", response_model=DeleteOut)
def delete_all(
    tenant_id: int, body: DeleteAllIn, admin: SuperAdminOnly, db: DbSession
) -> DeleteOut:
    """Delete every kind. `confirm` must be `DELETE`, `company_name` the company's exact name
    and `acknowledged` true. Counters of the emptied series go back to 1. 422
    CONFIRMATION_MISMATCH, COMPANY_NAME_MISMATCH, ACKNOWLEDGEMENT_REQUIRED."""
    return data.delete_all(
        db, tenant_id, body.confirm, body.company_name, body.acknowledged, admin.admin_id
    )


@router.get("/numbering", response_model=NumberingOut)
def get_numbering(tenant_id: int, _: SuperAdminOnly, db: DbSession) -> NumberingOut:
    """One row per shop, document type and financial year: the highest existing number (read
    from the documents), the configured next number and the next document written out."""
    return numbering.list_series(db, tenant_id)


@router.patch("/numbering", response_model=NumberingRow)
def set_numbering(
    tenant_id: int, body: NumberingSetIn, admin: SuperAdminOnly, db: DbSession
) -> NumberingRow:
    """Set a series' next number. It must be at least the highest existing number plus one
    (409 NUMBER_TOO_LOW); a reason is required. Audited with the old and new values."""
    return numbering.set_next(db, tenant_id, body, admin.admin_id)
