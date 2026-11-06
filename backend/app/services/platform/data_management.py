"""A Super Admin counts and deletes a company's business data (Milestone 26, ADR 0013).

This is the one place, besides the company restore, that removes ledger rows and issued
documents. It does so only inside `data_purge` (a platform session with `app.data_purge` on, set
for this transaction only), after a protected safety backup, under typed confirmations, in one
transaction, in catalogue order, with one DELETE per table. No TRUNCATE, no disabled constraint,
no `session_replication_role`. Files leave storage after the commit. Any failure rolls
everything back, is audited, and leaves the company as it was.

The company is read from the `tenant` table before anything is composed: a company id in a URL
is not authority over that company, and every statement filters on `tenant_id`.
"""

import logging
from collections.abc import Collection, Sequence
from typing import Any, cast

from sqlalchemy import CursorResult, Result, text
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError, NotFoundError, UnprocessableError
from app.domain import data_management as rules
from app.models.base import Base
from app.models.enums import BackupSource, PlatformAction
from app.models.tenancy import Tenant
from app.schemas.platform_data import (
    BlockedOut,
    BlockerOut,
    DataInventory,
    DataKindOut,
    DataPreviewOut,
    DataViewOut,
    DeleteOut,
    TableCountOut,
)
from app.services.platform import backups
from app.services.platform import numbering as numbering_admin
from app.services.platform.audit import record
from app.services.platform.data_catalogue import KINDS, LABELS, ORDER, Kind
from app.services.platform.purge import data_purge
from app.services.storage import get_storage

logger = logging.getLogger(__name__)


def _tenant(db: Session, tenant_id: int) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFoundError("No such company", code="TENANT_NOT_FOUND")
    return tenant


def _resolve(keys: Sequence[str] | str) -> list[str]:
    try:
        return rules.resolve(keys, ORDER)
    except rules.DataError as exc:
        raise UnprocessableError(str(exc), code=exc.code, field="keys") from exc


def _count(db: Session, table: str, tenant_id: int, where: str = "") -> int:
    return int(
        db.execute(
            text(f'SELECT count(*) FROM "{table}" WHERE tenant_id = :t {where}'),  # noqa: S608
            {"t": tenant_id},
        ).scalar_one()
    )


def _in(column: str, values: Collection[str], *, negate: bool = False) -> str:
    """A fixed list from the catalogue (never user input) as SQL."""
    listed = ", ".join(f"'{v}'" for v in sorted(values))
    return f"AND {column} {'NOT ' if negate else ''}IN ({listed})" if values else ""


def _refs_of(selection: Collection[str]) -> tuple[set[str], set[str], set[str]]:
    stock = {r for k in selection for r in KINDS[k].stock_refs}
    party = {r for k in selection for r in KINDS[k].party_refs}
    attach = {r for k in selection for r in KINDS[k].attachment_refs}
    return stock, party, attach


# ---------------------------------------------------------------------------- the inventory


def _referencing_rows(
    db: Session, tenant_id: int, kind: Kind, by: Kind, selection: Collection[str]
) -> int:
    """How many rows of `by` point at `kind` through a foreign key (the most of any one
    table). Ledger rows that a selected kind takes with it are not counted: they will be gone."""
    stock, party, _ = _refs_of(selection)
    best = 0
    for name in by.tables:
        for fk in Base.metadata.tables[name].foreign_keys:
            if fk.column.table.name not in kind.tables:
                continue
            where = f'AND "{fk.parent.name}" IS NOT NULL'
            if name == "stock_ledger":
                where += " " + _in("ref_type", stock, negate=True)
            if name == "party_ledger":
                where += " " + _in("ref_type", party, negate=True)
            best = max(best, _count(db, name, tenant_id, where))
    return best


def blockers(
    db: Session, tenant_id: int, key: str, selection: Collection[str] = ()
) -> dict[str, int]:
    """The kinds that still hold rows pointing at this one, with how many."""
    kind = KINDS[key]
    found = {
        r: _referencing_rows(db, tenant_id, kind, KINDS[r], selection) for r in kind.blocked_by
    }
    for r in kind.posted_by:
        found[r] = sum(_count(db, t, tenant_id) for t in KINDS[r].headline)
    return found


def _blocker_list(counts: dict[str, int]) -> list[BlockerOut]:
    return [
        BlockerOut(key=k, label=LABELS[k], count=n) for k in ORDER if (n := counts.get(k, 0)) > 0
    ]


def _kind_out(
    db: Session, tenant_id: int, kind: Kind, selection: Collection[str] = ()
) -> DataKindOut:
    tables = [TableCountOut(table=t, count=_count(db, t, tenant_id)) for t in kind.tables]
    held = _blocker_list(blockers(db, tenant_id, kind.key, selection))
    return DataKindOut(
        key=kind.key,
        label=kind.label,
        count=sum(c.count for c in tables if c.table in kind.headline),
        tables=tables,
        blocked_by=held,
        can_delete=not held,
    )


def inventory(db: Session, tenant_id: int) -> DataInventory:
    tenant = _tenant(db, tenant_id)
    items = [_kind_out(db, tenant_id, KINDS[k]) for k in ORDER]
    return DataInventory(company_name=tenant.name, items=items, total=sum(i.count for i in items))


def view(db: Session, tenant_id: int, key: str) -> DataViewOut:
    _tenant(db, tenant_id)
    if key not in KINDS:
        raise UnprocessableError(f"Unknown kind of data: {key}", code="UNKNOWN_DATA_KIND")
    kind = KINDS[key]
    rows = db.execute(text(kind.view.sql), {"t": tenant_id}).all()
    total = sum(_count(db, t, tenant_id) for t in kind.headline)
    return DataViewOut(
        key=key,
        label=kind.label,
        columns=list(kind.view.labels),
        rows=[[str(c) if c is not None else "" for c in r] for r in rows],
        total=total,
    )


# ---------------------------------------------------------------------------- preview


def _plan(db: Session, tenant_id: int, selection: Sequence[str]) -> tuple[dict[str, int], int]:
    """Rows that would go, per table (a selected kind's tables, and the ledger and attachment
    rows its documents posted), and how many stored files go with them."""
    full = {t for k in selection for t in KINDS[k].tables}
    plan: dict[str, int] = {}
    files = 0
    for key in selection:
        kind = KINDS[key]
        for table in kind.tables:
            plan[table] = _count(db, table, tenant_id)
        for table, column in kind.files:
            files += _count(db, table, tenant_id, f'AND "{column}" IS NOT NULL')
    extras = (
        ("stock_ledger", "stock_refs"),
        ("party_ledger", "party_refs"),
        ("attachment", "attachment_refs"),
    )
    for table, field in extras:
        if table in full:
            continue
        refs = {r for k in selection for r in getattr(KINDS[k], field)}
        n = _count(db, table, tenant_id, _in("ref_type", refs)) if refs else 0
        if n:
            plan[table] = n
            if table == "attachment":
                files += n
    return plan, files


def preview(db: Session, tenant_id: int, keys: Sequence[str] | str) -> DataPreviewOut:
    _tenant(db, tenant_id)
    selection = _resolve(keys)
    plan, files = _plan(db, tenant_id, selection)
    kinds = [_kind_out(db, tenant_id, KINDS[k], selection) for k in selection]
    held = rules.unselected_blockers(
        selection, {k.key: {b.key: b.count for b in k.blocked_by} for k in kinds}
    )
    out_blocked = [
        BlockedOut(key=k, label=LABELS[k], blocked_by=_blocker_list(by)) for k, by in held.items()
    ]
    return DataPreviewOut(
        everything=list(selection) == list(ORDER),
        kinds=kinds,
        tables=[TableCountOut(table=t, count=n) for t, n in plan.items()],
        total=sum(plan.values()),
        files=files,
        blocked=out_blocked,
        message=rules.blocked_message(held, LABELS) if held else None,
    )


# ---------------------------------------------------------------------------- deleting


def _removed(result: Result[Any]) -> int:
    return cast("CursorResult[Any]", result).rowcount


def _delete_kind(db: Session, tenant_id: int, kind: Kind) -> tuple[dict[str, int], list[str]]:
    """One kind's rows, child tables first, one statement each, then the ledger and attachment
    rows its documents posted. Returns rows removed per table and the stored files to remove."""
    counts: dict[str, int] = {}
    keys: list[str] = []
    for table in kind.tables:  # a row that points at another row of its own table
        for fk in Base.metadata.tables[table].foreign_keys:
            if fk.column.table.name == table:
                col = fk.parent.name
                sql = (
                    f'UPDATE "{table}" SET "{col}" = NULL '  # noqa: S608
                    f'WHERE tenant_id = :t AND "{col}" IS NOT NULL'
                )
                db.execute(text(sql), {"t": tenant_id})
    file_columns = dict(kind.files)
    for table in kind.tables:
        returning = f' RETURNING "{file_columns[table]}"' if table in file_columns else ""
        result = db.execute(
            text(f'DELETE FROM "{table}" WHERE tenant_id = :t{returning}'),  # noqa: S608
            {"t": tenant_id},
        )
        if returning:
            found = result.all()
            counts[table] = len(found)
            keys += [str(r[0]) for r in found if r[0]]
        else:
            counts[table] = _removed(result)
    for table, refs in (("stock_ledger", kind.stock_refs), ("party_ledger", kind.party_refs)):
        if refs:
            sql = f'DELETE FROM "{table}" WHERE tenant_id = :t {_in("ref_type", refs)}'  # noqa: S608
            counts[table] = counts.get(table, 0) + _removed(db.execute(text(sql), {"t": tenant_id}))
    if kind.attachment_refs:
        found = db.execute(
            text(
                "DELETE FROM attachment WHERE tenant_id = :t "  # noqa: S608
                f"{_in('ref_type', kind.attachment_refs)} RETURNING storage_key"
            ),
            {"t": tenant_id},
        ).all()
        counts["attachment"] = counts.get("attachment", 0) + len(found)
        keys += [str(r[0]) for r in found if r[0]]
    return counts, keys


def _remove_files(keys: Sequence[str]) -> int:
    """After the commit. A file that will not go is logged: the rows are gone either way."""
    store = get_storage()
    removed = 0
    for key in keys:
        try:
            store.delete(key)
            removed += 1
        except Exception:  # one stuck file must not hide the others
            logger.warning("Could not remove stored file %s after a data deletion", key)
    return removed


def _check_blockers(db: Session, tenant_id: int, selection: Sequence[str]) -> None:
    found = rules.unselected_blockers(
        selection, {k: blockers(db, tenant_id, k, selection) for k in selection}
    )
    if found:
        first = next(iter(found))
        raise ConflictError(
            rules.blocked_message(found, LABELS),
            code="DATA_BLOCKED",
            extra={
                "blocked": [
                    {"key": k, "blocked_by": [b.model_dump() for b in _blocker_list(by)]}
                    for k, by in found.items()
                ],
                "first": first,
            },
        )


def _fail(db: Session, tenant: Tenant, admin_id: int, operation: str, why: str) -> None:
    db.rollback()
    record(
        db,
        PlatformAction.COMPANY_DATA_DELETE_FAILED,
        admin_id,
        tenant_id=tenant.id,
        details={"operation": operation, "reason": why},
    )
    db.commit()


def _run(
    db: Session, tenant: Tenant, selection: list[str], admin_id: int, operation: str
) -> DeleteOut:
    note = f"Taken before deleting company data ({operation})"
    try:
        backup = backups.make_company_backup(
            db,
            tenant,
            source=BackupSource.SAFETY,
            protected=True,
            admin_id=admin_id,
            note=note,
        )
    except Exception as exc:
        _fail(db, tenant, admin_id, operation, "The safety backup failed")
        raise ConflictError(
            "The safety backup could not be made, so nothing was removed.",
            code="SAFETY_BACKUP_FAILED",
        ) from exc
    backup_id = backup.id
    try:
        totals: dict[str, int] = {}
        keys: list[str] = []
        with data_purge(db):
            for key in selection:  # catalogue order: what blocks a kind goes before it
                counts, files = _delete_kind(db, tenant.id, KINDS[key])
                for table, n in counts.items():
                    totals[table] = totals.get(table, 0) + n
                keys += files
            deleted_tables = {t for k in selection for t in KINDS[k].tables}
            series = numbering_admin.reset_emptied(
                db, tenant.id, deleted_tables, admin_id, f"Company data deleted ({operation})"
            )
        record(
            db,
            PlatformAction.COMPANY_DATA_DELETED_ALL
            if operation == "all"
            else PlatformAction.COMPANY_DATA_DELETED,
            admin_id,
            tenant_id=tenant.id,
            details={
                "operation": operation,
                "kinds": selection,
                "tables": totals,
                "total": sum(totals.values()),
                "backup_id": backup_id,
                "series_reset": [s.model_dump() for s in series],
            },
        )
        db.commit()
    except Exception as exc:
        _fail(db, tenant, admin_id, operation, type(exc).__name__)
        raise AppError(
            "The deletion failed and nothing was removed. The company is as it was.",
            code="DATA_DELETE_FAILED",
        ) from exc
    db.expire_all()
    removed = _remove_files(keys)
    return DeleteOut(
        operation="all" if operation == "all" else "selected",
        kinds=selection,
        tables=[TableCountOut(table=t, count=n) for t, n in totals.items()],
        total=sum(totals.values()),
        backup_id=backup_id,
        series_reset=series,
        files_removed=removed,
    )


def delete_selected(
    db: Session, tenant_id: int, keys: Sequence[str], confirm: str, admin_id: int
) -> DeleteOut:
    tenant = _tenant(db, tenant_id)
    selection = _resolve(keys)
    if not rules.selected_confirmation_ok(confirm):
        raise UnprocessableError(
            "Type DELETE exactly to delete", code="CONFIRMATION_MISMATCH", field="confirm"
        )
    _check_blockers(db, tenant_id, selection)
    return _run(db, tenant, selection, admin_id, "selected")


def delete_all(
    db: Session,
    tenant_id: int,
    confirm: str,
    company_name: str,
    acknowledged: bool,
    admin_id: int,
) -> DeleteOut:
    tenant = _tenant(db, tenant_id)
    if not rules.selected_confirmation_ok(confirm):
        raise UnprocessableError(
            "Type DELETE exactly to delete", code="CONFIRMATION_MISMATCH", field="confirm"
        )
    if company_name != tenant.name:
        raise UnprocessableError(
            "Type the company's exact name", code="COMPANY_NAME_MISMATCH", field="company_name"
        )
    if not rules.all_confirmation_ok(confirm, company_name, tenant.name, acknowledged):
        raise UnprocessableError(
            "Tick the box to confirm", code="ACKNOWLEDGEMENT_REQUIRED", field="acknowledged"
        )
    return _run(db, tenant, list(ORDER), admin_id, "all")
