"""Backup and recovery from the admin (Milestone 25, ADR 0013).

Long work (a dump, a company archive, a restore) never runs inside the request. The request
makes a `platform_backup_job` row and hands its id to a launcher; the page polls the job. The
launcher the API uses starts one daemon thread with its own database session (the smallest
thing that fits one `backend` container; a process that dies leaves a `running` job that goes
stale after six hours and never blocks anything). Tests pass a launcher that runs inline.

A platform restore is NOT run from here: replacing the database a web request runs on is not
safe. The admin shows `scripts/restore.sh` and its arguments instead (ADR 0013).
"""

import hashlib
import logging
import os
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.clock import SHOP_TZ
from app.core.config import StorageProvider, get_settings
from app.core.db import SessionLocal
from app.core.errors import AppError, BusinessRuleError, ConflictError, NotFoundError
from app.core.tenancy import PLATFORM_KEY, TENANT_KEY, set_platform, set_tenant
from app.domain import backups as rules
from app.models.enums import (
    BackupJobKind,
    BackupJobStatus,
    BackupKind,
    BackupSource,
    BackupStatus,
    PlatformAction,
)
from app.models.platform import (
    PlatformAdmin,
    PlatformBackup,
    PlatformBackupJob,
    PlatformBackupSchedule,
)
from app.models.tenancy import Tenant
from app.schemas.platform_backups import (
    BackupCompany,
    BackupCreate,
    BackupList,
    BackupOut,
    BackupSummary,
    JobOut,
    ScheduleIn,
    ScheduleOut,
    ToolOut,
)
from app.services import process_runner as tools
from app.services.maintenance import MaintenanceSwitch
from app.services.platform import company_archive as archive
from app.services.platform.audit import record

logger = logging.getLogger(__name__)

Launcher = Callable[[int], None]
UPLOAD_CHUNK = 1024 * 1024


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------- the folder


def folder_problem() -> str | None:
    raw = get_settings().backup_dir
    if not raw:
        return "BACKUP_DIR is not set, so backups cannot be kept."
    path = Path(raw)
    if not path.is_dir():
        return "The backup folder does not exist."
    if not os.access(path, os.W_OK):
        return "The backup folder cannot be written to by the API."
    return None


def folder() -> Path:
    problem = folder_problem()
    if problem:
        raise ConflictError(problem, code="BACKUP_FOLDER_UNAVAILABLE")
    return Path(get_settings().backup_dir)


def _need_tools(*names: str) -> None:
    missing = []
    for name in names:
        try:
            tools.find_tool(name)
        except tools.ToolMissingError:
            missing.append(name)
    if missing:
        raise ConflictError(
            f"These tools are not installed for the API: {', '.join(missing)}.",
            code="BACKUP_TOOLS_MISSING",
        )


# ---------------------------------------------------------------------------- reading


def _companies(db: Session) -> dict[int, BackupCompany]:
    return {
        t.id: BackupCompany(id=t.id, slug=t.slug, name=t.name) for t in db.scalars(select(Tenant))
    }


def _present(row: PlatformBackup) -> bool:
    try:
        return (folder() / row.file_name).is_file()
    except ConflictError:
        return False


def _out(
    row: PlatformBackup, companies: dict[int, BackupCompany], admins: dict[int, str]
) -> BackupOut:
    return BackupOut(
        id=row.id,
        kind=row.kind,
        source=row.source,
        company=companies.get(row.company_id) if row.company_id else None,
        file_name=row.file_name,
        files_name=row.files_name,
        size_bytes=row.size_bytes,
        sha256=row.sha256,
        schema_revision=row.schema_revision,
        status=row.status,
        started_at=row.started_at,
        completed_at=row.completed_at,
        protected=row.protected,
        note=row.note,
        error=row.error,
        created_by=admins.get(row.created_by_admin_id) if row.created_by_admin_id else None,
        file_present=_present(row),
        restore_command=(
            rules.restore_command(row.file_name)
            if row.kind is BackupKind.PLATFORM and rules.stamp_of_platform_name(row.file_name)
            else None
        ),
    )


def _admins(db: Session) -> dict[int, str]:
    return {a.id: a.full_name for a in db.scalars(select(PlatformAdmin))}


def list_backups(
    db: Session, kind: BackupKind | None, company_id: int | None, limit: int
) -> BackupList:
    query = select(PlatformBackup).order_by(
        PlatformBackup.started_at.desc(), PlatformBackup.id.desc()
    )
    if kind is not None:
        query = query.where(PlatformBackup.kind == kind)
    if company_id is not None:
        query = query.where(PlatformBackup.company_id == company_id)
    companies, admins = _companies(db), _admins(db)
    return BackupList(items=[_out(r, companies, admins) for r in db.scalars(query.limit(limit))])


def get_backup(db: Session, backup_id: int) -> PlatformBackup:
    row = db.get(PlatformBackup, backup_id)
    if row is None:
        raise NotFoundError("No such backup", code="BACKUP_NOT_FOUND")
    return row


def one(db: Session, backup_id: int) -> BackupOut:
    return _out(get_backup(db, backup_id), _companies(db), _admins(db))


def schedule_row(db: Session) -> PlatformBackupSchedule:
    row = db.get(PlatformBackupSchedule, 1)
    if row is None:  # a database built without migration 0038's insert
        row = PlatformBackupSchedule(id=1)
        db.add(row)
        db.flush()
    return row


def _next_run(row: PlatformBackupSchedule, now: datetime) -> datetime:
    return rules.next_scheduled(now, rules.parse_daily_time(row.daily_time), SHOP_TZ)


def summary(db: Session) -> BackupSummary:
    now = _now()
    live = now - rules.STALE_JOB_AFTER
    by_status = dict(
        db.execute(
            select(PlatformBackup.status, func.count()).group_by(PlatformBackup.status)
        ).all()
    )
    problem = folder_problem()
    return BackupSummary(
        last_backup_at=db.execute(
            select(func.max(PlatformBackup.completed_at)).where(
                PlatformBackup.status == BackupStatus.VERIFIED
            )
        ).scalar_one(),
        verified_count=by_status.get(BackupStatus.VERIFIED, 0),
        failed_count=by_status.get(BackupStatus.FAILED, 0),
        storage_bytes=db.execute(
            select(func.coalesce(func.sum(PlatformBackup.size_bytes), 0))
        ).scalar_one()
        or 0,
        next_scheduled_at=_next_run(schedule_row(db), now),
        running_jobs=db.execute(
            select(func.count()).where(
                PlatformBackupJob.status.in_((BackupJobStatus.QUEUED, BackupJobStatus.RUNNING)),
                PlatformBackupJob.created_at > live,
            )
        ).scalar_one(),
        folder_ready=problem is None,
        folder_problem=problem,
        tools=[ToolOut(name=t.name, found=t.path is not None) for t in tools.tool_status()],
        restore_command_example="./scripts/restore.sh backups/erp-YYYYMMDD-HHMM.dump",
    )


# ---------------------------------------------------------------------------- jobs


def _job_out(db: Session, job: PlatformBackupJob) -> JobOut:
    company = None
    if job.company_id:
        tenant = db.get(Tenant, job.company_id)
        company = (
            BackupCompany(id=tenant.id, slug=tenant.slug, name=tenant.name) if tenant else None
        )
    return JobOut(
        id=job.id,
        kind=job.kind,
        status=job.status,
        company=company,
        backup_id=job.backup_id,
        safety_backup_id=job.safety_backup_id,
        step=job.step,
        error_code=job.error_code,
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def get_job(db: Session, job_id: int) -> JobOut:
    job = db.get(PlatformBackupJob, job_id)
    if job is None:
        raise NotFoundError("No such job", code="JOB_NOT_FOUND")
    return _job_out(db, job)


def _tenant(db: Session, company_id: int | None) -> Tenant:
    if company_id is None:
        raise BusinessRuleError("Choose a company", code="COMPANY_REQUIRED", field="company_id")
    tenant = db.get(Tenant, company_id)
    if tenant is None:
        raise NotFoundError("No such company", code="TENANT_NOT_FOUND")
    return tenant


def _ensure_free(db: Session, kind: BackupJobKind, company_id: int | None) -> None:
    """One backup or restore at a time per company (and one platform backup)."""
    live = _now() - rules.STALE_JOB_AFTER
    query = select(func.count()).where(
        PlatformBackupJob.status.in_((BackupJobStatus.QUEUED, BackupJobStatus.RUNNING)),
        PlatformBackupJob.created_at > live,
    )
    if company_id is None:
        query = query.where(PlatformBackupJob.kind == BackupJobKind.BACKUP_PLATFORM)
    else:
        query = query.where(PlatformBackupJob.company_id == company_id)
    if db.execute(query).scalar_one():
        raise ConflictError(
            "A backup or restore is already running for this", code="BACKUP_JOB_RUNNING"
        )


def start_backup(db: Session, body: BackupCreate, admin_id: int, launch: Launcher) -> JobOut:
    if body.kind is BackupKind.PLATFORM:
        _need_tools("pg_dump", "pg_restore")
        kind, tenant = BackupJobKind.BACKUP_PLATFORM, None
    else:
        kind, tenant = BackupJobKind.BACKUP_COMPANY, _tenant(db, body.company_id)
    folder()
    _ensure_free(db, kind, tenant.id if tenant else None)
    job = PlatformBackupJob(
        kind=kind,
        status=BackupJobStatus.QUEUED,
        company_id=tenant.id if tenant else None,
        requested_by_admin_id=admin_id,
        note=(body.note or "").strip() or None,
    )
    db.add(job)
    db.flush()
    record(
        db,
        PlatformAction.BACKUP_CREATE,
        admin_id,
        tenant_id=tenant.id if tenant else None,
        details={"kind": body.kind.value, "job_id": job.id, "note": job.note},
    )
    db.commit()
    launch(job.id)
    db.refresh(job)
    return _job_out(db, job)


def start_restore(
    db: Session, backup_id: int, company_id: int, confirm: str, admin_id: int, launch: Launcher
) -> JobOut:
    """Restore one company from one of its archives. The archive must name this company and
    this schema revision (409 BACKUP_WRONG_COMPANY, BACKUP_SCHEMA_MISMATCH)."""
    if not rules.confirmation_ok(confirm, rules.CONFIRM_RESTORE):
        raise BusinessRuleError(
            "Type RESTORE exactly to restore", code="CONFIRMATION_MISMATCH", field="confirm"
        )
    source = get_backup(db, backup_id)
    tenant = _tenant(db, company_id)
    if source.kind is not BackupKind.COMPANY:
        raise ConflictError(
            "A platform backup is restored from the command line, not here",
            code="BACKUP_PLATFORM_RESTORE_CLI",
        )
    if source.status is not BackupStatus.VERIFIED:
        raise ConflictError("Only a verified backup can be restored", code="BACKUP_NOT_VERIFIED")
    path = folder() / source.file_name
    if not path.is_file():
        raise ConflictError(
            "The backup file is missing from the folder", code="BACKUP_FILE_MISSING"
        )
    if source.company_id != tenant.id:
        raise archive.ArchiveError(
            "This backup belongs to another company and cannot be restored onto this one",
            code="BACKUP_WRONG_COMPANY",
        )
    archive.check_for(archive.read_manifest(path), tenant, archive.schema_revision(db))
    _ensure_free(db, BackupJobKind.RESTORE_COMPANY, tenant.id)
    job = PlatformBackupJob(
        kind=BackupJobKind.RESTORE_COMPANY,
        status=BackupJobStatus.QUEUED,
        company_id=tenant.id,
        backup_id=source.id,
        requested_by_admin_id=admin_id,
    )
    db.add(job)
    db.flush()
    db.commit()
    launch(job.id)
    db.refresh(job)
    return _job_out(db, job)


def thread_launcher(switch: MaintenanceSwitch) -> Launcher:
    """The launcher the API uses: one daemon thread, one session of its own."""

    def launch(job_id: int) -> None:
        def work() -> None:
            with SessionLocal() as session:
                run_job(session, job_id, switch)

        threading.Thread(target=work, name=f"backup-job-{job_id}", daemon=True).start()

    return launch


def inline_launcher(db: Session, switch: MaintenanceSwitch) -> Launcher:
    """Runs the job now, on the caller's session (tests)."""
    return lambda job_id: run_job(db, job_id, switch)


def _fail_text(exc: Exception) -> tuple[str, str]:
    """A code and a message safe to show an admin: never a row, a path or a connection string."""
    if isinstance(exc, AppError):
        return exc.code, exc.message
    if isinstance(exc, tools.ToolFailedError | tools.ToolMissingError):
        return "BACKUP_TOOL_FAILED", str(exc)
    return "BACKUP_FAILED", "The job failed. The server log has the details."


def run_job(db: Session, job_id: int, switch: MaintenanceSwitch) -> None:
    """Do the job. Never raises: a failure is written on the job."""
    set_platform(db)
    job = db.get(PlatformBackupJob, job_id)
    if job is None:
        return
    job.status = BackupJobStatus.RUNNING
    job.started_at = _now()
    job.step = "Starting"
    db.commit()
    try:
        if job.kind is BackupJobKind.BACKUP_PLATFORM:
            job.step = "Dumping the database"
            db.commit()
            job.backup_id = make_platform_backup(
                db, source=BackupSource.MANUAL, admin_id=job.requested_by_admin_id, note=job.note
            ).id
        elif job.kind is BackupJobKind.BACKUP_COMPANY:
            job.step = "Packing the company"
            db.commit()
            job.backup_id = make_company_backup(
                db,
                _tenant(db, job.company_id),
                source=BackupSource.MANUAL,
                protected=False,
                admin_id=job.requested_by_admin_id,
                note=job.note,
            ).id
        else:
            _restore(db, job, switch)
        job.status = BackupJobStatus.SUCCEEDED
        job.step = "Done"
        job.finished_at = _now()
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("backup job %s failed", job_id)
        code, message = _fail_text(exc)
        job = db.get(PlatformBackupJob, job_id) or job
        job.status = BackupJobStatus.FAILED
        job.error_code, job.error_message = code, message
        job.finished_at = _now()
        if job.kind is BackupJobKind.RESTORE_COMPANY:
            record(
                db,
                PlatformAction.BACKUP_RESTORE_FAILED,
                job.requested_by_admin_id,
                tenant_id=job.company_id,
                details={
                    "backup_id": job.backup_id,
                    "safety_backup_id": job.safety_backup_id,
                    "code": code,
                    "message": message,
                },
            )
        db.commit()


# ---------------------------------------------------------------------------- making backups


def _unique_name(
    db: Session, make: Callable[[datetime], str], now: datetime
) -> tuple[str, datetime]:
    while db.execute(
        select(func.count()).where(PlatformBackup.file_name == make(now))
    ).scalar_one():
        now += timedelta(seconds=1)
    return make(now), now


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(UPLOAD_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _finish(row: PlatformBackup, path: Path, now: datetime) -> None:
    row.size_bytes = path.stat().st_size
    row.sha256 = _sha256(path)
    row.status = BackupStatus.VERIFIED
    row.completed_at = now


def make_company_backup(
    db: Session,
    tenant: Tenant,
    *,
    source: BackupSource,
    protected: bool,
    admin_id: int | None,
    note: str | None,
) -> PlatformBackup:
    """Pack one company into an archive, check it reads back, and record it."""
    target = folder()
    name, now = _unique_name(db, lambda n: rules.company_name(tenant.slug, n), _now())
    row = PlatformBackup(
        kind=BackupKind.COMPANY,
        source=source,
        company_id=tenant.id,
        file_name=name,
        status=BackupStatus.RUNNING,
        started_at=now,
        created_by_admin_id=admin_id,
        protected=protected,
        note=note,
    )
    db.add(row)
    db.commit()
    partial = target / f"{name}.partial"
    try:
        manifest = archive.build_archive(db, tenant, partial, now)
        archive.check_for(archive.read_manifest(partial), tenant, manifest["schema_revision"])
        partial.replace(target / name)
        row.schema_revision = manifest["schema_revision"]
        _finish(row, target / name, _now())
        db.commit()
    except Exception as exc:
        db.rollback()
        partial.unlink(missing_ok=True)
        failed = db.get(PlatformBackup, row.id) or row
        failed.status = BackupStatus.FAILED
        failed.error = _fail_text(exc)[1]
        failed.completed_at = _now()
        db.commit()
        raise
    return row


def _files_source() -> Path | None:
    settings = get_settings()
    if settings.storage_provider is not StorageProvider.LOCAL:
        return None
    path = Path(settings.storage_dir)
    return path if path.is_dir() else None


def make_platform_backup(
    db: Session, *, source: BackupSource, admin_id: int | None, note: str | None
) -> PlatformBackup:
    """`pg_dump --format=custom` and the files tarball, named as scripts/backup-loop.sh names
    them, verified with `pg_restore --list` and a SHA-256."""
    target = folder()
    pg_dump, pg_restore = tools.find_tool("pg_dump"), tools.find_tool("pg_restore")
    conn = rules.pg_connection(get_settings().database_url)
    name, now = _unique_name(db, lambda n: rules.platform_names(n)[0], _now())
    files_name = rules.platform_names(now)[1]
    files_dir = _files_source()
    row = PlatformBackup(
        kind=BackupKind.PLATFORM,
        source=source,
        file_name=name,
        files_name=files_name if files_dir else None,
        schema_revision=archive.schema_revision(db),
        status=BackupStatus.RUNNING,
        started_at=now,
        created_by_admin_id=admin_id,
        note=note,
    )
    db.add(row)
    db.commit()
    dump, files = target / name, target / files_name
    partials = [target / f"{name}.partial", target / f"{files_name}.partial"]
    try:
        env = rules.pg_env(conn)
        tools.run(rules.pg_dump_argv(pg_dump, conn, partials[0]), password=conn.password, env=env)
        tools.run(rules.pg_restore_list_argv(pg_restore, partials[0]))
        if files_dir:
            tar = tools.find_tool("tar")
            tools.run(rules.tar_create_argv(tar, partials[1], files_dir))
            tools.run(rules.tar_list_argv(tar, partials[1]))
            partials[1].replace(files)
        partials[0].replace(dump)
        _finish(row, dump, _now())
        db.commit()
    except Exception as exc:
        db.rollback()
        for partial in partials:
            partial.unlink(missing_ok=True)
        failed = db.get(PlatformBackup, row.id) or row
        failed.status = BackupStatus.FAILED
        failed.error = _fail_text(exc)[1]
        failed.completed_at = _now()
        db.commit()
        raise
    return row


# ---------------------------------------------------------------------------- restoring


def _restore(db: Session, job: PlatformBackupJob, switch: MaintenanceSwitch) -> None:
    tenant = _tenant(db, job.company_id)
    source = get_backup(db, job.backup_id or 0)
    path = folder() / source.file_name
    job.step = "Checking the archive"
    db.commit()
    manifest = archive.read_manifest(path)
    archive.check_for(manifest, tenant, archive.schema_revision(db))

    switch.begin_tenant_restore(tenant.id)
    try:
        job.step = "Taking a protected safety backup"
        db.commit()
        safety = make_company_backup(
            db,
            tenant,
            source=BackupSource.SAFETY,
            protected=True,
            admin_id=job.requested_by_admin_id,
            note=f"Taken before restoring backup #{source.id}",
        )
        job.safety_backup_id = safety.id
        job.step = "Checking the archive's files"
        db.commit()
        if source.sha256 and _sha256(path) != source.sha256:
            raise archive.ArchiveError(
                "The backup file no longer matches the checksum taken when it was made",
                code="BACKUP_CORRUPT",
            )
        with archive.unpack_verified(path, manifest) as root:
            job.step = "Restoring"
            db.flush()
            try:
                set_tenant(db, tenant.id)
                archive.replace_company_rows(db, tenant, manifest, root)
                job.step = "Checking the restored books"
                archive.run_checks(db)
            finally:
                db.info.pop(TENANT_KEY, None)
            record(
                db,
                PlatformAction.BACKUP_RESTORE,
                job.requested_by_admin_id,
                tenant_id=tenant.id,
                details={
                    "backup_id": source.id,
                    "safety_backup_id": safety.id,
                    "tables": len(manifest["tables"]),
                    "files": len(manifest["files"]),
                },
            )
            db.commit()
        db.expire_all()
    finally:
        switch.end_tenant_restore(tenant.id)
        db.info.pop(TENANT_KEY, None)
        if db.info.get(PLATFORM_KEY) is None:
            set_platform(db)


# -------------------------------------------------------------- download, upload, delete


def download_path(db: Session, backup_id: int, part: str, admin_id: int) -> tuple[Path, str]:
    row = get_backup(db, backup_id)
    if row.status is not BackupStatus.VERIFIED:
        raise ConflictError("Only a verified backup can be downloaded", code="BACKUP_NOT_VERIFIED")
    name = row.file_name
    if part == "files":
        if not row.files_name:
            raise NotFoundError("This backup has no files archive", code="BACKUP_NO_FILES")
        name = row.files_name
    path = folder() / name
    if not rules.is_stored_name(name) or not path.is_file():
        raise ConflictError(
            "The backup file is missing from the folder", code="BACKUP_FILE_MISSING"
        )
    record(
        db,
        PlatformAction.BACKUP_DOWNLOAD,
        admin_id,
        tenant_id=row.company_id,
        details={"backup_id": row.id, "file": name},
    )
    db.commit()
    return path, name


def delete_backup(db: Session, backup_id: int, confirm: str, admin_id: int) -> None:
    if not rules.confirmation_ok(confirm, rules.CONFIRM_DELETE):
        raise BusinessRuleError(
            "Type DELETE exactly to delete", code="CONFIRMATION_MISMATCH", field="confirm"
        )
    row = get_backup(db, backup_id)
    if row.protected:
        raise ConflictError(
            "A protected backup is a safety copy and is never deleted", code="BACKUP_PROTECTED"
        )
    if row.status is BackupStatus.RUNNING:
        raise ConflictError("This backup is still being made", code="BACKUP_RUNNING")
    base = folder()
    for name in (row.file_name, row.files_name):
        if name and rules.is_stored_name(name):
            (base / name).unlink(missing_ok=True)
    record(
        db,
        PlatformAction.BACKUP_DELETE,
        admin_id,
        tenant_id=row.company_id,
        details={"backup_id": row.id, "file": row.file_name, "source": row.source.value},
    )
    db.execute(
        update(PlatformBackupJob)
        .where(PlatformBackupJob.backup_id == row.id)
        .values(backup_id=None)
    )
    db.delete(row)
    db.commit()


def upload(db: Session, file: UploadFile, admin_id: int) -> BackupOut:
    """Accept a company archive for a later restore: `.tar.gz` only, within the size limit, and
    only when its manifest names a company here and this schema revision."""
    target = folder()
    if rules.upload_problem(file.filename, 1) is not None:
        raise BusinessRuleError("Upload a .tar.gz company archive", code="UPLOAD_NOT_TAR_GZ")
    partial = target / f"upload-{os.getpid()}-{threading.get_ident()}.partial"
    size = 0
    try:
        with partial.open("wb") as out:
            while chunk := file.file.read(UPLOAD_CHUNK):
                size += len(chunk)
                if size > rules.MAX_UPLOAD_BYTES:
                    raise BusinessRuleError("The archive is too large", code="FILE_TOO_LARGE")
                out.write(chunk)
        problem = rules.upload_problem(file.filename, size)
        if problem == "EMPTY":
            raise BusinessRuleError("The archive is empty", code="UPLOAD_EMPTY")
        manifest = archive.read_manifest(partial)
        if (
            rules.check_manifest(manifest, tenant_id=-1, tenant_slug="", revision="")
            is rules.ArchiveProblem.INVALID
        ):
            raise archive.ArchiveError(
                "This is not a company backup archive", code="BACKUP_INVALID"
            )
        tenant = db.get(Tenant, manifest["tenant_id"])
        if tenant is None or tenant.slug != manifest["tenant_slug"]:
            raise archive.ArchiveError(
                "This archive names a company that is not here", code="BACKUP_WRONG_COMPANY"
            )
        archive.check_for(manifest, tenant, archive.schema_revision(db))
        name, now = _unique_name(db, lambda n: rules.company_name(tenant.slug, n), _now())
        partial.replace(target / name)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    row = PlatformBackup(
        kind=BackupKind.COMPANY,
        source=BackupSource.UPLOADED,
        company_id=tenant.id,
        file_name=name,
        schema_revision=manifest["schema_revision"],
        status=BackupStatus.RUNNING,
        started_at=now,
        created_by_admin_id=admin_id,
        note="Uploaded for a restore",
    )
    _finish(row, target / name, _now())
    db.add(row)
    db.flush()
    record(
        db,
        PlatformAction.BACKUP_UPLOAD,
        admin_id,
        tenant_id=tenant.id,
        details={"backup_id": row.id, "size_bytes": row.size_bytes},
    )
    db.commit()
    return one(db, row.id)


# -------------------------------------------------------------- schedule and retention


def get_schedule(db: Session) -> ScheduleOut:
    row = schedule_row(db)
    return ScheduleOut(
        daily_time=row.daily_time,
        keep_daily=row.keep_daily,
        keep_weekly=row.keep_weekly,
        keep_monthly=row.keep_monthly,
        updated_at=row.updated_at,
        next_scheduled_at=_next_run(row, _now()),
    )


def set_schedule(db: Session, body: ScheduleIn, admin_id: int) -> ScheduleOut:
    try:
        at = rules.parse_daily_time(body.daily_time)
    except ValueError as exc:
        raise BusinessRuleError(str(exc), code="BAD_TIME", field="daily_time") from exc
    for field in ("keep_daily", "keep_weekly", "keep_monthly"):
        if not rules.retention_ok(getattr(body, field)):
            raise BusinessRuleError(
                "Keep between 0 and 365 copies", code="BAD_RETENTION", field=field
            )
    row = schedule_row(db)
    before = {
        "daily_time": row.daily_time,
        "keep_daily": row.keep_daily,
        "keep_weekly": row.keep_weekly,
        "keep_monthly": row.keep_monthly,
    }
    row.daily_time = rules.format_daily_time(at)
    row.keep_daily, row.keep_weekly, row.keep_monthly = (
        body.keep_daily,
        body.keep_weekly,
        body.keep_monthly,
    )
    row.updated_by_admin_id = admin_id
    record(
        db,
        PlatformAction.BACKUP_SCHEDULE_UPDATE,
        admin_id,
        details={"before": before, "after": body.model_dump()},
    )
    db.commit()
    db.refresh(row)
    return get_schedule(db)


def prune(db: Session, now: datetime | None = None) -> int:
    """Delete the nightly copies the schedule no longer keeps. Protected, manual, safety,
    uploaded and company backups are never touched."""
    now = now or _now()
    schedule = schedule_row(db)
    rows = list(db.scalars(select(PlatformBackup)))
    facts = [
        rules.BackupFacts(
            r.id, r.started_at, r.protected, r.source.value, r.kind.value, r.status.value
        )
        for r in rows
    ]
    doomed = set(
        rules.backups_to_prune(
            facts,
            keep_daily=schedule.keep_daily,
            keep_weekly=schedule.keep_weekly,
            keep_monthly=schedule.keep_monthly,
            today=now.astimezone(SHOP_TZ).date(),
            tz=SHOP_TZ,
        )
    )
    base = Path(get_settings().backup_dir) if get_settings().backup_dir else None
    for row in rows:
        if row.id not in doomed:
            continue
        if base:
            for name in (row.file_name, row.files_name):
                if name and rules.is_stored_name(name):
                    (base / name).unlink(missing_ok=True)
        db.execute(
            update(PlatformBackupJob)
            .where(PlatformBackupJob.backup_id == row.id)
            .values(backup_id=None)
        )
        db.delete(row)
    db.commit()
    return len(doomed)


def record_scheduled_start(db: Session, now: datetime) -> tuple[int, str, str]:
    """The nightly loop is about to dump: note it, and say what to call the files."""
    name, stamp_now = _unique_name(db, lambda n: rules.platform_names(n)[0], now)
    files_name = rules.platform_names(stamp_now)[1]
    row = PlatformBackup(
        kind=BackupKind.PLATFORM,
        source=BackupSource.SCHEDULED,
        file_name=name,
        files_name=files_name,
        schema_revision=archive.schema_revision(db),
        status=BackupStatus.RUNNING,
        started_at=stamp_now,
    )
    db.add(row)
    db.commit()
    return row.id, name, files_name


def record_scheduled_finish(db: Session, backup_id: int, ok: bool, error: str | None) -> None:
    row = get_backup(db, backup_id)
    base = Path(get_settings().backup_dir)
    dump = base / row.file_name
    files = base / row.files_name if row.files_name else None
    if files is not None and not files.is_file():
        row.files_name = None  # nothing was kept on a volume
    if ok and dump.is_file():
        _finish(row, dump, _now())
    else:
        row.status = BackupStatus.FAILED
        row.error = (error or "The nightly backup failed")[:500]
        row.completed_at = _now()
    db.commit()
