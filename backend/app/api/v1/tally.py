"""Tally export for the accountant (FM4, finance review F5). Owner and accountant only."""

from datetime import date

from fastapi import APIRouter, Response

from app.api.deps import DbSession, OwnerOrAccountant
from app.schemas.tally import TallyLedgersOut, TallyLedgersPut, TallyPreviewOut
from app.services import tally as service

router = APIRouter(prefix="/tally", tags=["tally"])


@router.get("/ledgers", response_model=TallyLedgersOut)
def read_ledgers(_: OwnerOrAccountant, db: DbSession) -> TallyLedgersOut:
    """The ledger names the export uses, with the defaults the accountant can change."""
    return service.read_ledgers(db)


@router.put("/ledgers", response_model=TallyLedgersOut)
def save_ledgers(
    body: TallyLedgersPut, principal: OwnerOrAccountant, db: DbSession
) -> TallyLedgersOut:
    return service.save_ledgers(db, body, actor_id=principal.user_id)


@router.get("/preview", response_model=TallyPreviewOut)
def preview(_: OwnerOrAccountant, db: DbSession, date_from: date, date_to: date) -> TallyPreviewOut:
    """What the export would contain, and whether it agrees with GSTR-1, GSTR-3B and the dues."""
    return service.preview(db, date_from, date_to)


@router.get("/export", response_class=Response)
def export(
    principal: OwnerOrAccountant,
    db: DbSession,
    date_from: date,
    date_to: date,
    masters: bool = True,
) -> Response:
    """The day book as a Tally XML import file (`masters=false` leaves out the ledger masters)."""
    xml = service.export_xml(db, date_from, date_to, masters=masters, actor_id=principal.user_id)
    name = f"tally-{date_from.isoformat()}-to-{date_to.isoformat()}.xml"
    return Response(
        xml,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
