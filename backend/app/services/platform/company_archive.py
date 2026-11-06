"""One company's backup archive and its restore (Milestone 25, ADR 0013).

An archive is a `.tar.gz` with `manifest.json`, `tables/<table>.csv` for every table that has a
`tenant_id` (rows of that company only, made with `COPY (SELECT ... WHERE tenant_id = :id)`, never
a filtered `pg_dump`) and `files/<key>` for the company's attachments, logo and closing PDFs.

Which tables:
- restored: every table with `tenant_id` except the three below;
- exported but never overwritten: `audit_log` (the company's own trail, as in WA);
- deleted on restore but never exported: `auth_session` (everyone signs in again);
- never touched: Duolink's own rows (`platform_audit_log`, `subscription`,
  `subscription_payment`), so a restore cannot rewrite what a company has paid Duolink.
"""

import csv
import hashlib
import json
import sys
import tarfile
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from psycopg import sql
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.sql.schema import Table

from app.core.errors import ConflictError
from app.domain import backups as rules
from app.models import Base
from app.models.tenancy import Tenant
from app.services import verify
from app.services.platform.purge import data_purge
from app.services.storage import StorageError, get_storage

PLATFORM_OWNED = frozenset({"platform_audit_log", "subscription", "subscription_payment"})
EXPORT_ONLY = frozenset({"audit_log"})
DELETE_ONLY = frozenset({"auth_session"})
MAX_MANIFEST_BYTES = 5 * 1024 * 1024
MAX_UNPACKED_BYTES = 4 * 1024 * 1024 * 1024
CHUNK = 1024 * 1024


class ArchiveError(ConflictError):
    """The archive cannot be used. Codes: BACKUP_INVALID, BACKUP_CORRUPT."""


# ---------------------------------------------------------------------------- the tables


def _company_tables() -> dict[str, Table]:
    return {
        t.name: t
        for t in Base.metadata.sorted_tables
        if "tenant_id" in t.c and t.name not in PLATFORM_OWNED
    }


def _deps(names: set[str]) -> dict[str, set[str]]:
    tables = _company_tables()
    return {
        n: {fk.column.table.name for fk in tables[n].foreign_keys if fk.column.table.name in names}
        for n in names
    }


def restored_tables() -> list[str]:
    """Tables loaded on restore, parents first."""
    names = set(_company_tables()) - EXPORT_ONLY - DELETE_ONLY
    return rules.dependency_order(_deps(names))


def exported_tables() -> list[str]:
    names = set(_company_tables()) - DELETE_ONLY
    return rules.dependency_order(_deps(names))


def deleted_tables() -> list[str]:
    """Tables emptied on restore, children first."""
    names = set(_company_tables()) - EXPORT_ONLY
    return rules.reverse_order(_deps(names))


def _columns(db: Session, table: str) -> list[str]:
    """The stored columns, in order. A generated column is left out: it cannot be copied in."""
    rows = db.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t AND is_generated = 'NEVER' "
            "ORDER BY ordinal_position"
        ),
        {"t": table},
    ).scalars()
    return list(rows)


def schema_revision(db: Session) -> str:
    return str(db.execute(text("SELECT version_num FROM alembic_version")).scalar_one())


def _raw(db: Session) -> Any:
    """The psycopg connection under this session, so COPY runs in the same transaction."""
    return db.connection().connection.driver_connection


# ---------------------------------------------------------------------------- building


def _file_keys(db: Session, tenant_id: int) -> list[str]:
    keys: set[str] = set()
    params = {"t": tenant_id}
    queries = (
        "SELECT storage_key FROM attachment WHERE tenant_id = :t",
        "SELECT pdf_key FROM daily_closing WHERE tenant_id = :t AND pdf_key IS NOT NULL",
        "SELECT logo_key FROM shop_settings WHERE tenant_id = :t AND logo_key IS NOT NULL",
    )
    for query in queries:
        keys.update(k for k in db.execute(text(query), params).scalars() if k)
    return sorted(k for k in keys if rules.is_safe_member(f"files/{k}"))


def _sha_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _count_rows(path: Path) -> int:
    csv.field_size_limit(min(sys.maxsize, 2**30))
    with path.open("r", newline="", encoding="utf-8") as handle:
        return max(sum(1 for _ in csv.reader(handle)) - 1, 0)


def build_archive(db: Session, tenant: Tenant, dest: Path, now: datetime) -> dict[str, Any]:
    """Write the archive at `dest` (a `.partial` name; the caller renames it) and return its
    manifest. The session must be a platform session."""
    conn = _raw(db)
    tables: dict[str, dict[str, Any]] = {}
    files: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    with tempfile.TemporaryDirectory(prefix="company-backup-") as scratch:
        root = Path(scratch)
        (root / "tables").mkdir()
        for name in exported_tables():
            columns = _columns(db, name)
            query = sql.SQL(
                "COPY (SELECT {cols} FROM {t} WHERE tenant_id = {tid}) "
                "TO STDOUT WITH (FORMAT csv, HEADER true)"
            ).format(
                cols=sql.SQL(", ").join(sql.Identifier(c) for c in columns),
                t=sql.Identifier(name),
                tid=sql.Literal(tenant.id),
            )
            target = root / "tables" / f"{name}.csv"
            with conn.cursor() as cur, cur.copy(query) as copy, target.open("wb") as out:
                for chunk in copy:
                    out.write(bytes(chunk))
            tables[name] = {"rows": _count_rows(target), "sha256": _sha_of(target)}
        store = get_storage()
        for key in _file_keys(db, tenant.id):
            try:
                data = store.get(key)
            except StorageError:
                missing.append(key)
                continue
            target = root / "files" / key
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            files[key] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        manifest: dict[str, Any] = {
            "format": rules.MANIFEST_FORMAT,
            "tenant_id": tenant.id,
            "tenant_slug": tenant.slug,
            "schema_revision": schema_revision(db),
            "created_at": now.astimezone(UTC).isoformat(),
            "tables": tables,
            "files": files,
            "missing_files": missing,
        }
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
        with tarfile.open(dest, "w:gz") as tar:
            tar.add(manifest_path, arcname="manifest.json")
            for name in tables:
                tar.add(root / "tables" / f"{name}.csv", arcname=f"tables/{name}.csv")
            for key in files:
                tar.add(root / "files" / key, arcname=f"files/{key}")
    return manifest


# ---------------------------------------------------------------------------- reading


def read_manifest(path: Path) -> dict[str, Any]:
    """The manifest of an archive, after checking that every member is a plain file with a safe
    name and that the archive does not unpack to something absurd. ArchiveError BACKUP_INVALID."""
    try:
        with tarfile.open(path, "r:gz") as tar:
            manifest_bytes: bytes | None = None
            total = 0
            for member in tar:
                if not member.isfile() or not rules.is_safe_member(member.name):
                    raise ArchiveError(
                        "The archive holds something that is not allowed", code="BACKUP_INVALID"
                    )
                total += member.size
                if total > MAX_UNPACKED_BYTES:
                    raise ArchiveError(
                        "The archive unpacks to too much data", code="BACKUP_INVALID"
                    )
                if member.name == "manifest.json":
                    if member.size > MAX_MANIFEST_BYTES:
                        raise ArchiveError("The manifest is too large", code="BACKUP_INVALID")
                    handle = tar.extractfile(member)
                    manifest_bytes = handle.read() if handle else None
            if manifest_bytes is None:
                raise ArchiveError("The archive has no manifest", code="BACKUP_INVALID")
        parsed = json.loads(manifest_bytes)
    except (tarfile.TarError, OSError, EOFError, ValueError) as exc:
        if isinstance(exc, ArchiveError):
            raise
        raise ArchiveError("This is not a company backup archive", code="BACKUP_INVALID") from exc
    if not isinstance(parsed, dict):
        raise ArchiveError("The manifest is not an object", code="BACKUP_INVALID")
    return parsed


def check_for(manifest: dict[str, Any], tenant: Tenant, revision: str) -> None:
    """409 BACKUP_INVALID, BACKUP_WRONG_COMPANY or BACKUP_SCHEMA_MISMATCH."""
    problem = rules.check_manifest(
        manifest, tenant_id=tenant.id, tenant_slug=tenant.slug, revision=revision
    )
    if problem is rules.ArchiveProblem.WRONG_COMPANY:
        raise ArchiveError(
            "This backup belongs to another company and cannot be restored onto this one",
            code=problem.value,
        )
    if problem is rules.ArchiveProblem.SCHEMA_MISMATCH:
        raise ArchiveError(
            "This backup was made on another version of the database and cannot be restored",
            code=problem.value,
        )
    if problem is not None:
        raise ArchiveError("This is not a company backup archive", code=problem.value)


@contextmanager
def unpack_verified(path: Path, manifest: dict[str, Any]) -> Iterator[Path]:
    """Unpack into a scratch folder, checking every member's SHA-256 against the manifest while
    writing. ArchiveError BACKUP_CORRUPT on a mismatch, a missing or an unlisted member."""
    expected: dict[str, str] = {
        f"tables/{t}.csv": e["sha256"] for t, e in manifest["tables"].items()
    } | {f"files/{k}": e["sha256"] for k, e in manifest["files"].items()}
    with tempfile.TemporaryDirectory(prefix="company-restore-") as scratch:
        root = Path(scratch)
        seen: set[str] = set()
        try:
            with tarfile.open(path, "r:gz") as tar:
                for member in tar:
                    if member.name == "manifest.json":
                        continue
                    if not member.isfile() or not rules.is_safe_member(member.name):
                        raise ArchiveError(
                            "The archive holds something that is not allowed", code="BACKUP_INVALID"
                        )
                    want = expected.get(member.name)
                    handle = tar.extractfile(member)
                    if want is None or handle is None:
                        raise ArchiveError(
                            f"{member.name} is not listed in the manifest", code="BACKUP_CORRUPT"
                        )
                    target = root / member.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    digest = hashlib.sha256()
                    with target.open("wb") as out:
                        while chunk := handle.read(CHUNK):
                            digest.update(chunk)
                            out.write(chunk)
                    if digest.hexdigest() != want:
                        raise ArchiveError(
                            f"{member.name} does not match its checksum", code="BACKUP_CORRUPT"
                        )
                    seen.add(member.name)
        except (tarfile.TarError, OSError, EOFError) as exc:
            raise ArchiveError("The archive cannot be read", code="BACKUP_CORRUPT") from exc
        missing = sorted(set(expected) - seen)
        if missing:
            raise ArchiveError(f"{missing[0]} is missing from the archive", code="BACKUP_CORRUPT")
        yield root


# ---------------------------------------------------------------------------- restoring


def _reset_sequence(db: Session, table: str) -> None:
    if "id" not in _columns(db, table):  # a composite key, such as company_counter
        return
    seq = db.execute(
        text("SELECT pg_get_serial_sequence(:t, 'id')"), {"t": f"public.{table}"}
    ).scalar_one_or_none()
    if seq:
        db.execute(
            text(
                f"SELECT setval(:seq, GREATEST(COALESCE((SELECT MAX(id) FROM {table}), 1), "  # noqa: S608
                f"(SELECT last_value FROM {seq})))"
            ),
            {"seq": seq},
        )


def replace_company_rows(db: Session, tenant: Tenant, manifest: dict[str, Any], root: Path) -> None:
    """Inside the caller's transaction: delete the company's rows (children first), copy the
    archive's rows in (parents first), reset the id counters and put the files back. The
    caller runs the checks and commits, or rolls everything back."""
    conn = _raw(db)
    with data_purge(db):
        for name in deleted_tables():
            db.execute(text(f'DELETE FROM "{name}" WHERE tenant_id = :t'), {"t": tenant.id})  # noqa: S608
    for name in restored_tables():
        if name not in manifest["tables"]:
            raise ArchiveError(f"The archive has no rows for {name}", code="BACKUP_INVALID")
        columns = _columns(db, name)
        # COPY FROM is refused on a table with row-level security, so the rows go through a
        # plain temporary table (same columns, no constraints) and one INSERT ... SELECT.
        cols = sql.SQL(", ").join(sql.Identifier(c) for c in columns)
        stage = sql.Identifier(f"restore_{name}")
        csv_path = root / "tables" / f"{name}.csv"
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "CREATE TEMP TABLE {s} ON COMMIT DROP AS SELECT {c} FROM {t} WITH NO DATA"
                ).format(s=stage, c=cols, t=sql.Identifier(name))
            )
            copy_in = sql.SQL("COPY {s} ({c}) FROM STDIN WITH (FORMAT csv, HEADER match)").format(
                s=stage, c=cols
            )
            with cur.copy(copy_in) as copy, csv_path.open("rb") as src:
                while chunk := src.read(CHUNK):
                    copy.write(chunk)
            cur.execute(
                sql.SQL("INSERT INTO {t} ({c}) SELECT {c} FROM {s}").format(
                    t=sql.Identifier(name), c=cols, s=stage
                )
            )
            cur.execute(sql.SQL("DROP TABLE {s}").format(s=stage))
    for name in restored_tables():
        _reset_sequence(db, name)
    store = get_storage()
    for key in manifest["files"]:
        store.put(key, (root / "files" / key).read_bytes())


def run_checks(db: Session) -> None:
    """The same checks as `python -m app.scripts.verify`, for this company. A failure raises,
    and the caller rolls the restore back."""
    result = verify.run_checks(db)
    failed = [c.name for c in result.checks if c.state == "fail"]
    if failed:
        raise ArchiveError(
            "The restored books failed the integrity check: " + ", ".join(failed),
            code="RESTORE_VERIFY_FAILED",
        )
