"""Backup and recovery rules (Milestone 25, ADR 0013).

Pure: file names, the archive manifest check, the foreign-key order, the retention rule, the
schedule and the command lines for the tools. No database, no files, no clock: callers pass
`now` and `today`. The command lines never carry a password; it goes in the environment.
"""

import heapq
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

CONFIRM_RESTORE = "RESTORE"
CONFIRM_DELETE = "DELETE"
MANIFEST_FORMAT = 1
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
STALE_JOB_AFTER = timedelta(hours=6)
TOOLS = frozenset({"pg_dump", "pg_restore", "tar"})

_PLATFORM_DUMP = re.compile(r"^erp-(\d{8}-\d{4})\.dump$")
_PLATFORM_FILES = re.compile(r"^erp-files-\d{8}-\d{4}\.tar\.gz$")
_COMPANY_ARCHIVE = re.compile(r"^company-[a-z0-9-]+-\d{8}-\d{6}\.tar\.gz$")
_TABLE = re.compile(r"^[a-z][a-z0-9_]*$")
_TABLE_CSV = re.compile(r"^[a-z][a-z0-9_]*\.csv$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DAILY_TIME = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def confirmation_ok(typed: str | None, expected: str) -> bool:
    """Typed confirmations are compared exactly, case and spaces included."""
    return typed == expected


# ---------------------------------------------------------------------------- names


def platform_names(now: datetime) -> tuple[str, str]:
    """The dump and the files archive, named as scripts/backup-loop.sh names them."""
    stamp = now.strftime("%Y%m%d-%H%M")
    return f"erp-{stamp}.dump", f"erp-files-{stamp}.tar.gz"


def stamp_of_platform_name(name: str) -> str | None:
    found = _PLATFORM_DUMP.match(name)
    return found.group(1) if found else None


def company_name(slug: str, now: datetime) -> str:
    return f"company-{slug}-{now.strftime('%Y%m%d-%H%M%S')}.tar.gz"


def is_stored_name(name: str) -> bool:
    """A file name we made ourselves: nothing else is ever read from or written to the folder."""
    return bool(
        _PLATFORM_DUMP.match(name) or _PLATFORM_FILES.match(name) or _COMPANY_ARCHIVE.match(name)
    )


def restore_command(dump_name: str) -> str:
    """What the operator runs to restore the whole platform. The admin shows it, never runs it."""
    if not _PLATFORM_DUMP.match(dump_name):
        raise ValueError("not a platform dump name")
    return f"./scripts/restore.sh backups/{dump_name}"


# ---------------------------------------------------------------------------- the archive


class ArchiveProblem(StrEnum):
    WRONG_COMPANY = "BACKUP_WRONG_COMPANY"
    SCHEMA_MISMATCH = "BACKUP_SCHEMA_MISMATCH"
    INVALID = "BACKUP_INVALID"


def is_table_name(name: str) -> bool:
    return bool(_TABLE.match(name))


def is_safe_member(name: str) -> bool:
    """Only `manifest.json`, `tables/<table>.csv` and `files/<key>` are ever read from an
    archive, and never a path that leaves the folder."""
    if name == "manifest.json":
        return True
    if name.startswith("tables/"):
        return bool(_TABLE_CSV.match(name[len("tables/") :]))
    if name.startswith("files/"):
        if "\\" in name or "\x00" in name:
            return False
        parts = name[len("files/") :].split("/")
        return all(p not in ("", ".", "..") for p in parts)
    return False


def _entry_ok(entry: Any, key: str) -> bool:
    return (
        isinstance(entry, dict)
        and isinstance(entry.get(key), int)
        and not isinstance(entry.get(key), bool)
        and entry[key] >= 0
        and isinstance(entry.get("sha256"), str)
        and bool(_SHA256.match(entry["sha256"]))
    )


def _manifest_shape_ok(manifest: Any) -> bool:
    if not isinstance(manifest, dict) or manifest.get("format") != MANIFEST_FORMAT:
        return False
    tenant_id = manifest.get("tenant_id")
    if not isinstance(tenant_id, int) or isinstance(tenant_id, bool):
        return False
    if not isinstance(manifest.get("tenant_slug"), str):
        return False
    if not isinstance(manifest.get("schema_revision"), str):
        return False
    tables, files = manifest.get("tables"), manifest.get("files")
    if not isinstance(tables, dict) or not isinstance(files, dict):
        return False
    if not all(is_table_name(t) and _entry_ok(e, "rows") for t, e in tables.items()):
        return False
    return all(is_safe_member(f"files/{k}") and _entry_ok(e, "size") for k, e in files.items())


def check_manifest(
    manifest: Mapping[str, Any], *, tenant_id: int, tenant_slug: str, revision: str
) -> ArchiveProblem | None:
    """Is this archive of this company, and of the schema now in the database?"""
    if not _manifest_shape_ok(manifest):
        return ArchiveProblem.INVALID
    if manifest["tenant_id"] != tenant_id or manifest["tenant_slug"] != tenant_slug:
        return ArchiveProblem.WRONG_COMPANY
    if manifest["schema_revision"] != revision:
        return ArchiveProblem.SCHEMA_MISMATCH
    return None


def dependency_order(deps: Mapping[str, set[str]]) -> list[str]:
    """Parents before children, ties broken by name so the order is the same every time.
    A table that points at itself, or at one outside the set, is not held up by it."""
    waiting = {t: {d for d in ds if d in deps and d != t} for t, ds in deps.items()}
    ready = [t for t, ds in waiting.items() if not ds]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        table = heapq.heappop(ready)
        order.append(table)
        for other, ds in waiting.items():
            if table in ds:
                ds.discard(table)
                if not ds:
                    heapq.heappush(ready, other)
    if len(order) != len(deps):
        raise ValueError("foreign keys form a cycle")
    return order


def reverse_order(deps: Mapping[str, set[str]]) -> list[str]:
    return list(reversed(dependency_order(deps)))


def upload_problem(filename: str | None, size: int) -> str | None:
    if not filename or not filename.endswith(".tar.gz"):
        return "NOT_TAR_GZ"
    if size <= 0:
        return "EMPTY"
    if size > MAX_UPLOAD_BYTES:
        return "TOO_LARGE"
    return None


# ---------------------------------------------------------------------------- schedule


def parse_daily_time(text: str) -> time:
    found = _DAILY_TIME.match(text) if isinstance(text, str) else None
    if not found:
        raise ValueError("The time must be HH:MM, 00:00 to 23:59")
    return time(int(found.group(1)), int(found.group(2)))


def format_daily_time(at: time) -> str:
    return at.strftime("%H:%M")


def retention_ok(count: int) -> bool:
    return isinstance(count, int) and not isinstance(count, bool) and 0 <= count <= 365


def next_scheduled(now: datetime, at: time, tz: tzinfo) -> datetime:
    """The next time the nightly backup is due, in the zone `now` was given in."""
    local = now.astimezone(tz)
    day = local.date()
    candidate = datetime.combine(day, at, tz)
    if candidate <= local:
        candidate = datetime.combine(day + timedelta(days=1), at, tz)
    return candidate.astimezone(now.tzinfo)


@dataclass(frozen=True)
class BackupFacts:
    id: int
    created_at: datetime
    protected: bool
    source: str  # scheduled, manual, safety, uploaded
    kind: str  # platform, company
    status: str  # running, verified, failed


def backups_to_prune(
    facts: Sequence[BackupFacts],
    *,
    keep_daily: int,
    keep_weekly: int,
    keep_monthly: int,
    today: date,
    tz: tzinfo,
) -> list[int]:
    """Which scheduled platform backups to delete. Only unprotected nightly copies are ever
    considered: manual, safety, uploaded, company and running backups are never pruned. Of the
    rest, the newest of each of the latest `keep_daily` days, `keep_weekly` weeks and
    `keep_monthly` months stay; a failed run keeps nothing."""
    pruned: list[int] = []
    good: list[tuple[date, datetime, int]] = []
    for f in facts:
        if f.kind != "platform" or f.source != "scheduled" or f.protected:
            continue
        day = f.created_at.astimezone(tz).date()
        if f.status == "running" or day > today:
            continue
        if f.status == "failed":
            pruned.append(f.id)
            continue
        good.append((day, f.created_at, f.id))
    good.sort(key=lambda g: g[1], reverse=True)

    keep: set[int] = set()

    def newest_per(bucket: Any, count: int) -> None:
        seen: list[Any] = []
        for day, _, ident in good:
            key = bucket(day)
            if key in seen:
                continue
            seen.append(key)
            if len(seen) <= count:
                keep.add(ident)

    newest_per(lambda d: d, keep_daily)
    newest_per(lambda d: d.isocalendar()[:2], keep_weekly)
    newest_per(lambda d: (d.year, d.month), keep_monthly)
    pruned.extend(ident for _, _, ident in good if ident not in keep)
    return sorted(pruned)


def job_is_stale(started_at: datetime | None, now: datetime) -> bool:
    """A job that began long ago and never finished belongs to a process that died."""
    return started_at is None or now - started_at > STALE_JOB_AFTER


# ---------------------------------------------------------------------------- processes


@dataclass(frozen=True)
class PgConnection:
    host: str
    port: int
    user: str
    dbname: str
    password: str


def pg_connection(url: str) -> PgConnection:
    parts = urlsplit(url)
    dbname = parts.path.lstrip("/")
    if not parts.scheme.startswith("postgresql") or not dbname:
        raise ValueError("DATABASE_URL is not a PostgreSQL URL with a database name")
    return PgConnection(
        host=parts.hostname or "localhost",
        port=parts.port or 5432,
        user=unquote(parts.username or ""),
        dbname=unquote(dbname),
        password=unquote(parts.password or ""),
    )


def pg_dump_argv(exe: Path, conn: PgConnection, out: Path) -> list[str]:
    return [
        str(exe),
        "--format=custom",
        f"--file={out}",
        f"--host={conn.host}",
        f"--port={conn.port}",
        f"--username={conn.user}",
        f"--dbname={conn.dbname}",
        "--no-password",
    ]


def pg_restore_list_argv(exe: Path, dump: Path) -> list[str]:
    return [str(exe), "--list", str(dump)]


def tar_create_argv(exe: Path, out: Path, source: Path) -> list[str]:
    return [str(exe), "-czf", str(out), "-C", str(source), "."]


def tar_list_argv(exe: Path, archive: Path) -> list[str]:
    return [str(exe), "-tzf", str(archive)]


def pg_env(conn: PgConnection) -> dict[str, str]:
    """The password travels in the environment, where `ps` does not show it."""
    return {"PGPASSWORD": conn.password} if conn.password else {}


def assert_no_secret(argv: Sequence[str], password: str) -> None:
    """The password as an argument, inside a URL (`:pw@`), or a `--password` flag."""
    if not password:
        return
    for arg in argv:
        if arg == password or f":{password}@" in arg or arg.lower().startswith("--password="):
            raise ValueError("a password must not be on a command line")


def tool_dirs(bin_dir: str) -> list[str]:
    """Where a tool may be found: PG_BIN_DIR first, then the usual system folders. Never a
    lookup on PATH, and never a folder from a request."""
    return ([bin_dir] if bin_dir else []) + ["/usr/bin", "/usr/local/bin", "/bin"]
