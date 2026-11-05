"""Backup and recovery in the admin (Milestone 25).

Files, sizes, checksums and statuses only: never a company's figures. Field names avoid the
words the admin money test looks for.
"""

from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field

from app.domain.backups import CONFIRM_RESTORE
from app.models.enums import BackupJobKind, BackupJobStatus, BackupKind, BackupSource, BackupStatus
from app.schemas.common import Schema


class BackupCompany(Schema):
    id: int
    slug: str
    name: str


class BackupOut(Schema):
    id: int
    kind: BackupKind
    source: BackupSource
    company: BackupCompany | None
    file_name: str
    files_name: str | None
    size_bytes: int | None
    sha256: str | None
    schema_revision: str | None
    status: BackupStatus
    started_at: datetime
    completed_at: datetime | None
    protected: bool
    note: str | None
    error: str | None
    created_by: str | None
    file_present: bool
    # Platform backups only: the command an operator runs. The admin never runs it.
    restore_command: str | None


class BackupList(Schema):
    items: list[BackupOut]


class ToolOut(Schema):
    name: str
    found: bool


class BackupSummary(Schema):
    last_backup_at: datetime | None
    verified_count: int
    failed_count: int
    storage_bytes: int
    next_scheduled_at: datetime
    running_jobs: int
    folder_ready: bool
    folder_problem: str | None
    tools: list[ToolOut]
    restore_command_example: str


class JobOut(Schema):
    id: int
    kind: BackupJobKind
    status: BackupJobStatus
    company: BackupCompany | None
    backup_id: int | None
    safety_backup_id: int | None
    step: str | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class BackupCreate(Schema):
    kind: BackupKind
    company_id: int | None = None
    note: str | None = Field(default=None, max_length=300)


class RestoreIn(Schema):
    """`confirm` must be `RESTORE`, typed exactly. `company_id` is the company to restore onto."""

    model_config = ConfigDict(str_strip_whitespace=False)

    company_id: int
    confirm: str = Field(default="", max_length=20, description=CONFIRM_RESTORE)


class DeleteIn(Schema):
    model_config = ConfigDict(str_strip_whitespace=False)

    confirm: str = Field(default="", max_length=20)


class ScheduleOut(Schema):
    daily_time: str
    keep_daily: int
    keep_weekly: int
    keep_monthly: int
    updated_at: datetime | None
    next_scheduled_at: datetime


class ScheduleIn(Schema):
    daily_time: str = Field(max_length=5)
    keep_daily: int = Field(ge=0, le=365)
    keep_weekly: int = Field(ge=0, le=365)
    keep_monthly: int = Field(ge=0, le=365)


Part = Literal["dump", "files"]
