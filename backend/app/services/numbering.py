"""Gapless document numbers (rule B16).

The counter row is incremented with an atomic upsert inside the caller's transaction. A
second transaction asking for the same series waits on the row lock until the first commits
or rolls back, so numbers are never skipped or repeated. Call this in the SAME transaction
that saves the document, never in a separate one.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.domain.fiscal import format_doc_number, fy_label
from app.models.enums import DocType
from app.models.numbering import DocumentSequence
from app.models.setup import Location

# Suffix added to the location code so each document type has its own series.
SERIES_SUFFIX: dict[DocType, str] = {
    DocType.SALES_INVOICE: "",
    DocType.CREDIT_NOTE: "C",
    DocType.DEBIT_NOTE: "D",
    DocType.DELIVERY_CHALLAN: "DC",
    DocType.PURCHASE_ENTRY: "P",
    DocType.PAYMENT_RECEIPT: "R",
}


def allocate_number(
    db: Session,
    *,
    location_id: int,
    doc_type: DocType,
    on: date,
    fy_start_month: int = 4,
    tenant_id: int = 1,
) -> str:
    code = db.execute(select(Location.code).where(Location.id == location_id)).scalar_one()
    fy = fy_label(on, fy_start_month)
    stmt = (
        insert(DocumentSequence)
        .values(
            tenant_id=tenant_id,
            location_id=location_id,
            doc_type=doc_type,
            financial_year=fy,
            next_value=2,
        )
        .on_conflict_do_update(
            index_elements=["tenant_id", "location_id", "doc_type", "financial_year"],
            set_={"next_value": DocumentSequence.next_value + 1},
        )
        .returning(DocumentSequence.next_value)
    )
    sequence = db.execute(stmt).scalar_one() - 1
    return format_doc_number(code + SERIES_SUFFIX[doc_type], fy, sequence)
