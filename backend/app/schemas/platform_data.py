"""Company data management and numbering in the admin (Milestone 26).

Counts, statuses and identifying text only: never an amount. Field names avoid the words the
admin money test looks for.
"""

from typing import Literal

from pydantic import ConfigDict, Field

from app.models.enums import DocType
from app.schemas.common import Schema


class TableCountOut(Schema):
    table: str
    count: int


class BlockerOut(Schema):
    key: str
    label: str
    count: int


class DataKindOut(Schema):
    key: str
    label: str
    count: int
    tables: list[TableCountOut]
    blocked_by: list[BlockerOut]
    can_delete: bool


class DataInventory(Schema):
    company_name: str
    items: list[DataKindOut]
    total: int


class DataViewOut(Schema):
    key: str
    label: str
    columns: list[str]
    rows: list[list[str]]
    total: int


class BlockedOut(Schema):
    key: str
    label: str
    blocked_by: list[BlockerOut]


class DataPreviewOut(Schema):
    everything: bool
    kinds: list[DataKindOut]
    tables: list[TableCountOut]
    total: int
    files: int
    blocked: list[BlockedOut]
    message: str | None


class DeleteSelectedIn(Schema):
    # Typed confirmations are compared exactly, spaces included: no trimming here.
    model_config = ConfigDict(str_strip_whitespace=False)

    keys: list[str] = Field(min_length=1, max_length=40)
    confirm: str = Field(max_length=40)


class DeleteAllIn(Schema):
    model_config = ConfigDict(str_strip_whitespace=False)

    confirm: str = Field(max_length=40)
    company_name: str = Field(max_length=200)
    acknowledged: bool


class SeriesMoveOut(Schema):
    series: str
    from_number: int
    to_number: int


class DeleteOut(Schema):
    operation: Literal["selected", "all"]
    kinds: list[str]
    tables: list[TableCountOut]
    total: int
    backup_id: int
    series_reset: list[SeriesMoveOut]
    files_removed: int


class NumberingRow(Schema):
    location_id: int
    location_code: str
    doc_type: DocType
    doc_label: str
    financial_year: str
    prefix: str
    highest_existing: int | None
    highest_number: str | None
    configured_next: int
    minimum_next: int
    next_document: str
    ahead_of_documents: bool
    suggested_next: int | None


class NumberingOut(Schema):
    items: list[NumberingRow]


class NumberingSetIn(Schema):
    location_id: int
    doc_type: DocType
    financial_year: str = Field(pattern=r"^\d\d(-\d\d)?$")
    next_number: int
    reason: str = Field(max_length=2000)
