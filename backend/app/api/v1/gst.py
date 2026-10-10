import json
from typing import Annotated

from fastapi import APIRouter, File, Form, Response, UploadFile, status

from app.api.deps import DbSession, OwnerOrAccountant
from app.core.clock import today_ist
from app.core.config import get_settings
from app.schemas.gst import Gstr1, Gstr2bResult, Gstr3b, ImportOut, ItcAtRiskOut
from app.services import gst_returns as service

router = APIRouter(prefix="/gst", tags=["gst"])


@router.get("/gstr1", response_model=Gstr1)
def gstr1(_: OwnerOrAccountant, db: DbSession, period: str) -> Gstr1:
    """GSTR-1 tables for a month (`2026-10`): B2B, B2CL, B2CS, credit notes, HSN, documents."""
    return service.gstr1(db, period)


@router.get("/gstr1/export", response_class=Response)
def gstr1_export(
    _: OwnerOrAccountant, db: DbSession, period: str, format: str = "json"
) -> Response:
    """Download GSTR-1 as the portal's offline-tool JSON, or as an Excel workbook (`xlsx`)."""
    data = service.gstr1(db, period)
    if format == "xlsx":
        return Response(
            service.gstr1_workbook(data),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="GSTR1-{period}.xlsx"'},
        )
    return Response(
        json.dumps(service.gstr1_portal_json(data), indent=1),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="GSTR1-{period}.json"'},
    )


@router.get("/gstr3b", response_model=Gstr3b)
def gstr3b(_: OwnerOrAccountant, db: DbSession, period: str) -> Gstr3b:
    """GSTR-3B figures for a month: outward supplies, input tax and tax payable per head."""
    return service.gstr3b(db, period)


@router.post("/gstr2b", response_model=ImportOut, status_code=status.HTTP_201_CREATED)
def import_gstr2b(
    principal: OwnerOrAccountant,
    db: DbSession,
    period: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> ImportOut:
    """Upload the GSTR-2B download for a month (portal JSON, or the simple CSV)."""
    limit = get_settings().max_upload_mb * 1024 * 1024
    row = service.import_2b(
        db,
        period,
        file.filename or "gstr2b",
        file.file.read(limit + 1)[:limit],
        actor_id=principal.user_id,
    )
    return ImportOut.model_validate(row)


@router.get("/gstr2b", response_model=Gstr2bResult)
def match_gstr2b(_: OwnerOrAccountant, db: DbSession, period: str) -> Gstr2bResult:
    """Our purchase bills matched to the latest GSTR-2B upload for the month."""
    return service.match_2b(db, period)


@router.get("/itc-at-risk", response_model=ItcAtRiskOut)
def itc_at_risk(_: OwnerOrAccountant, db: DbSession, period: str) -> ItcAtRiskOut:
    """Input tax on supplier bills in our books that GSTR-2B does not show, and the GST payable
    estimate from GSTR-3B. No figure is made up when no GSTR-2B is imported."""
    return service.itc_at_risk(db, period, today_ist())
