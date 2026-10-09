from fastapi import APIRouter

from app.api.deps import DbSession, OwnerOnly
from app.schemas.system import StatusOut, VerifyOut
from app.services import verify

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status", response_model=StatusOut)
def system_status(_: OwnerOnly, db: DbSession) -> StatusOut:
    """Is the system healthy: database version, last backup, file storage, e-way provider,
    and any shop whose previous day was not closed."""
    return verify.status(db)


@router.post("/verify", response_model=VerifyOut)
def run_verify(_: OwnerOnly, db: DbSession, full: bool = False) -> VerifyOut:
    """Re-add the books and compare with what is stored. Read-only; `full` also re-reads files."""
    return verify.run_checks(db, full=full)
