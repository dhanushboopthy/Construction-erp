"""A company's number series, seen and set by a Super Admin (Milestone 26, ADR 0013).

The series prefix in this ERP is the location code plus the document type's `SERIES_SUFFIX`, so
there is no free-text prefix to edit. The counter is only ever moved up through here (to at
least the highest existing number plus one); a data deletion moves the counters of the series it
emptied back to 1 (`reset_emptied`). Both write a `document_sequence_event` so `verify` can
explain the gap.
"""

from collections.abc import Collection

from sqlalchemy import insert, select, text, update
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, UnprocessableError
from app.domain import numbering as rules
from app.models.enums import DocType, PlatformAction, SequenceChange
from app.models.numbering import DocumentSequence, DocumentSequenceEvent
from app.models.setup import Location
from app.models.tenancy import Tenant
from app.schemas.platform_data import NumberingOut, NumberingRow, NumberingSetIn, SeriesMoveOut
from app.services.numbering import SERIES_SUFFIX
from app.services.platform.audit import record

# Where each series' documents live: (table, column holding the shop, extra condition).
SOURCES: dict[DocType, tuple[str, str, str]] = {
    DocType.SALES_INVOICE: ("sales_invoice", "location_id", ""),
    DocType.CREDIT_NOTE: ("credit_note", "location_id", ""),
    DocType.DEBIT_NOTE: ("debit_note", "location_id", ""),
    DocType.DELIVERY_CHALLAN: ("stock_transfer", "from_location_id", ""),
    DocType.PURCHASE_ENTRY: ("purchase", "location_id", ""),
    DocType.PAYMENT_RECEIPT: ("payment", "location_id", ""),
    DocType.CASH_VOUCHER: ("cash_entry", "location_id", ""),
    DocType.STOCK_ADJUSTMENT: ("stock_adjustment", "location_id", ""),
    DocType.BAD_DEBT_WRITEOFF: ("bad_debt_writeoff", "location_id", ""),
    DocType.STOCK_WRITEDOWN: ("stock_writedown", "location_id", ""),
    DocType.PURCHASE_ORDER: ("purchase_order", "location_id", ""),
    DocType.GOODS_RECEIPT: ("goods_receipt", "location_id", ""),
    DocType.QUOTATION: ("sales_quote", "location_id", "AND kind = 'quotation'"),
    DocType.PROFORMA: ("sales_quote", "location_id", "AND kind = 'proforma'"),
}


def _tenant(db: Session, tenant_id: int) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFoundError("No such company", code="TENANT_NOT_FOUND")
    return tenant


def highest_existing(
    db: Session, tenant_id: int, doc_type: DocType, location_id: int, fy: str
) -> tuple[int | None, str | None]:
    """The highest sequence among the surviving documents of one series, and its number. A
    cancelled bill is still a row, so it counts; a deleted one is gone, so it does not. Matched
    on the shop and the financial year, never on the prefix."""
    table, column, extra = SOURCES[doc_type]
    row = db.execute(
        text(
            f"SELECT number, split_part(number, '/', 3)::int FROM {table} "  # noqa: S608
            f"WHERE tenant_id = :t AND {column} = :l AND split_part(number, '/', 2) = :fy "
            f"AND number ~ '^[^/]+/[^/]+/[0-9]+$' {extra} "
            "ORDER BY split_part(number, '/', 3)::int DESC LIMIT 1"
        ),
        {"t": tenant_id, "l": location_id, "fy": fy},
    ).first()
    return (row[1], row[0]) if row else (None, None)


def _row(
    db: Session, tenant_id: int, code: str, seq: DocumentSequence | tuple[int, DocType, str, int]
) -> NumberingRow:
    if isinstance(seq, DocumentSequence):
        location_id, doc_type, fy, configured = (
            seq.location_id,
            seq.doc_type,
            seq.financial_year,
            seq.next_value,
        )
    else:
        location_id, doc_type, fy, configured = seq
    high, high_text = highest_existing(db, tenant_id, doc_type, location_id, fy)
    prefix = code + SERIES_SUFFIX[doc_type]
    try:
        written = rules.next_document(prefix, fy, configured)
    except ValueError:  # a longer number than the 16 characters a bill may carry
        written = f"{prefix}/{fy}/{configured:05d}"
    return NumberingRow(
        location_id=location_id,
        location_code=code,
        doc_type=doc_type,
        doc_label=rules.label_of(doc_type.value),
        financial_year=fy,
        prefix=prefix,
        highest_existing=high,
        highest_number=high_text,
        configured_next=configured,
        minimum_next=rules.floor_for(high),
        next_document=written,
        ahead_of_documents=rules.is_ahead(configured, high),
        suggested_next=rules.suggested_next(configured, high),
    )


def list_series(db: Session, tenant_id: int) -> NumberingOut:
    _tenant(db, tenant_id)
    rows = db.execute(
        select(DocumentSequence, Location.code)
        .join(Location, Location.id == DocumentSequence.location_id)
        .where(DocumentSequence.tenant_id == tenant_id)
        .order_by(Location.code, DocumentSequence.financial_year.desc(), DocumentSequence.doc_type)
    ).all()
    return NumberingOut(items=[_row(db, tenant_id, code, seq) for seq, code in rows])


def set_next(db: Session, tenant_id: int, body: NumberingSetIn, admin_id: int) -> NumberingRow:
    _tenant(db, tenant_id)
    location = db.execute(
        select(Location).where(Location.id == body.location_id, Location.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if location is None:
        raise NotFoundError("No such shop in this company", code="LOCATION_NOT_FOUND")
    try:
        reason = rules.clean_reason(body.reason)
    except rules.NumberingError as exc:
        raise UnprocessableError(str(exc), code="REASON_REQUIRED", field="reason") from exc
    try:
        existing = db.execute(
            select(DocumentSequence)
            .where(
                DocumentSequence.tenant_id == tenant_id,
                DocumentSequence.location_id == body.location_id,
                DocumentSequence.doc_type == body.doc_type,
                DocumentSequence.financial_year == body.financial_year,
            )
            .with_for_update()
        ).scalar_one_or_none()
        high, high_text = highest_existing(
            db, tenant_id, body.doc_type, body.location_id, body.financial_year
        )
        rules.check_next(body.next_number, high, high_text, body.doc_type.value)
    except rules.NumberingError as exc:
        raise ConflictError(str(exc), code="NUMBER_TOO_LOW", field="next_number") from exc
    old = existing.next_value if existing else 1
    if existing is None:
        db.execute(
            insert(DocumentSequence).values(
                tenant_id=tenant_id,
                location_id=body.location_id,
                doc_type=body.doc_type,
                financial_year=body.financial_year,
                next_value=body.next_number,
            )
        )
    else:
        db.execute(
            update(DocumentSequence)
            .where(
                DocumentSequence.tenant_id == tenant_id,
                DocumentSequence.location_id == body.location_id,
                DocumentSequence.doc_type == body.doc_type,
                DocumentSequence.financial_year == body.financial_year,
            )
            .values(next_value=body.next_number)
        )
    db.execute(
        insert(DocumentSequenceEvent).values(
            tenant_id=tenant_id,
            location_id=body.location_id,
            doc_type=body.doc_type,
            financial_year=body.financial_year,
            change=SequenceChange.SET,
            from_value=old,
            to_value=body.next_number,
            floor_value=rules.floor_for(high),
            reason=reason,
            admin_id=admin_id,
        )
    )
    record(
        db,
        PlatformAction.NUMBERING_SET,
        admin_id,
        tenant_id=tenant_id,
        details={
            "location": location.code,
            "doc_type": body.doc_type.value,
            "financial_year": body.financial_year,
            "old_next": old,
            "new_next": body.next_number,
            "highest_existing": high,
            "reason": reason,
        },
    )
    db.commit()
    series = (body.location_id, body.doc_type, body.financial_year, body.next_number)
    return _row(db, tenant_id, location.code, series)


def reset_emptied(
    db: Session, tenant_id: int, deleted_tables: Collection[str], admin_id: int, reason: str
) -> list[SeriesMoveOut]:
    """Inside the caller's transaction: every series whose documents lived only in the tables
    just emptied goes back to 1, and each move is recorded. Series with no change, and series of
    documents that were not touched, stay as they are."""
    moved: list[SeriesMoveOut] = []
    emptied = [d for d, (table, _, _) in SOURCES.items() if table in deleted_tables]
    rows = db.execute(
        select(DocumentSequence, Location.code)
        .join(Location, Location.id == DocumentSequence.location_id)
        .where(DocumentSequence.tenant_id == tenant_id, DocumentSequence.doc_type.in_(emptied))
        .where(DocumentSequence.next_value != 1)
        .order_by(Location.code, DocumentSequence.financial_year, DocumentSequence.doc_type)
    ).all()
    for seq, code in rows:
        old = seq.next_value
        db.execute(
            update(DocumentSequence)
            .where(
                DocumentSequence.tenant_id == tenant_id,
                DocumentSequence.location_id == seq.location_id,
                DocumentSequence.doc_type == seq.doc_type,
                DocumentSequence.financial_year == seq.financial_year,
            )
            .values(next_value=1)
        )
        db.execute(
            insert(DocumentSequenceEvent).values(
                tenant_id=tenant_id,
                location_id=seq.location_id,
                doc_type=seq.doc_type,
                financial_year=seq.financial_year,
                change=SequenceChange.RESET,
                from_value=old,
                to_value=1,
                floor_value=1,
                reason=reason,
                admin_id=admin_id,
            )
        )
        moved.append(
            SeriesMoveOut(
                series=f"{code}{SERIES_SUFFIX[seq.doc_type]}/{seq.financial_year}",
                from_number=old,
                to_number=1,
            )
        )
    return moved
