"""Backup and recovery (Milestone 25, ADR 0013). Every admin lists backups and sees their
status; only a Super Admin creates, downloads, uploads, restores, deletes or sets the schedule.
Long work runs as a job: the call answers 202 with a job id and the page polls
`GET /backups/jobs/{id}`. A platform restore is a command-line runbook (`scripts/restore.sh`),
shown here and never run."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import DbSession, PlatformAdminUser, SuperAdminOnly
from app.models.enums import BackupKind
from app.schemas.platform_backups import (
    BackupCreate,
    BackupList,
    BackupOut,
    BackupSummary,
    DeleteIn,
    JobOut,
    Part,
    RestoreIn,
    ScheduleIn,
    ScheduleOut,
)
from app.services.platform import backups as service

router = APIRouter(prefix="/backups", tags=["admin"])


def launcher(request: Request) -> service.Launcher:
    launch: service.Launcher = request.app.state.backup_launcher
    return launch


Launch = Annotated[service.Launcher, Depends(launcher)]


@router.get("", response_model=BackupList)
def list_backups(
    _: PlatformAdminUser,
    db: DbSession,
    kind: BackupKind | None = None,
    company_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> BackupList:
    """Every backup, newest first: nightly, manual, safety copies and uploads."""
    return service.list_backups(db, kind, company_id, limit)


@router.get("/summary", response_model=BackupSummary)
def summary(_: PlatformAdminUser, db: DbSession) -> BackupSummary:
    """Last backup, how many are verified, space used, the next scheduled run, and whether the
    folder and the tools (`pg_dump`, `pg_restore`, `tar`) are there."""
    return service.summary(db)


@router.get("/schedule", response_model=ScheduleOut)
def get_schedule(_: PlatformAdminUser, db: DbSession) -> ScheduleOut:
    return service.get_schedule(db)


@router.put("/schedule", response_model=ScheduleOut)
def set_schedule(body: ScheduleIn, admin: SuperAdminOnly, db: DbSession) -> ScheduleOut:
    """The nightly time (shop time, HH:MM) and how many daily, weekly and monthly copies to keep
    (Super Admin). 409 BAD_TIME, BAD_RETENTION. Audited."""
    return service.set_schedule(db, body, admin.admin_id)


@router.post("", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def create_backup(
    body: BackupCreate, admin: SuperAdminOnly, db: DbSession, launch: Launch
) -> JobOut:
    """Back up the whole platform (`kind: platform`) or one company (`kind: company`,
    `company_id`). Answers a job to poll. 409 BACKUP_TOOLS_MISSING, BACKUP_FOLDER_UNAVAILABLE,
    BACKUP_JOB_RUNNING, COMPANY_REQUIRED."""
    return service.start_backup(db, body, admin.admin_id, launch)


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, _: PlatformAdminUser, db: DbSession) -> JobOut:
    return service.get_job(db, job_id)


@router.post("/upload", response_model=BackupOut, status_code=status.HTTP_201_CREATED)
def upload(admin: SuperAdminOnly, db: DbSession, file: Annotated[UploadFile, File()]) -> BackupOut:
    """Keep a company archive for a later restore. `.tar.gz` only, 200 MB at most, and its
    manifest must name a company here and this schema revision. 409 BACKUP_INVALID,
    BACKUP_WRONG_COMPANY, BACKUP_SCHEMA_MISMATCH."""
    return service.upload(db, file, admin.admin_id)


@router.get("/{backup_id}/download")
def download(
    backup_id: int,
    admin: SuperAdminOnly,
    db: DbSession,
    part: Part = "dump",
) -> FileResponse:
    """Stream the backup file (`part=files` for a platform backup's files archive). Audited."""
    path, name = service.download_path(db, backup_id, part, admin.admin_id)
    return FileResponse(path, filename=name, media_type="application/octet-stream")


@router.post("/{backup_id}/restore", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def restore(
    backup_id: int, body: RestoreIn, admin: SuperAdminOnly, db: DbSession, launch: Launch
) -> JobOut:
    """Replace one company's data with a company archive. `confirm` must be `RESTORE`. A safety
    backup is taken first and kept; the company answers 403 TENANT_RESTORING meanwhile; any
    failure rolls everything back. 409 BACKUP_WRONG_COMPANY, BACKUP_SCHEMA_MISMATCH,
    BACKUP_NOT_VERIFIED, BACKUP_FILE_MISSING, BACKUP_JOB_RUNNING."""
    return service.start_restore(
        db, backup_id, body.company_id, body.confirm, admin.admin_id, launch
    )


@router.delete("/{backup_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(backup_id: int, body: DeleteIn, admin: SuperAdminOnly, db: DbSession) -> None:
    """Delete an unprotected backup and its files. `confirm` must be `DELETE`.
    409 BACKUP_PROTECTED, BACKUP_RUNNING."""
    service.delete_backup(db, backup_id, body.confirm, admin.admin_id)
