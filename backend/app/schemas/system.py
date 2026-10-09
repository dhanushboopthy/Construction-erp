from datetime import date, datetime
from typing import Literal

from app.schemas.common import Schema

CheckState = Literal["ok", "warn", "fail"]


class Check(Schema):
    name: str
    state: CheckState
    detail: str


class StatusOut(Schema):
    version: str
    environment: str
    test_watermark: bool  # true outside production: every PDF is stamped TEST
    database: CheckState
    migrations: Check
    backup: Check
    last_backup_at: datetime | None
    storage: Check
    gsp: Check
    unclosed: list[str]  # shops whose previous day is still open
    as_of: date


class VerifyOut(Schema):
    ok: bool
    checks: list[Check]
