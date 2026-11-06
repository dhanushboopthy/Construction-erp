"""The installable app and "force update" (Milestone 29)."""

from datetime import datetime

from pydantic import BaseModel, Field


class AppUpdateOut(BaseModel):
    """Where the platform's release generation stands, and which backend build is running.
    Counts and names only: no company's data."""

    generation: int
    forced_at: datetime | None
    forced_by: str | None  # the Super Admin's name
    backend_version: str
    backend_build: str


class ForceUpdateIn(BaseModel):
    reason: str | None = Field(default=None, max_length=200)
