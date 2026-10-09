from fastapi import APIRouter, Response, status

from app.api.deps import DbSession, OwnerOnly, OwnerOrCounter
from app.schemas.approvals import ApprovalOut, ApprovalRequest, PinSet
from app.services import approvals as approval_service
from app.services.users import get_user

router = APIRouter(tags=["approvals"])


@router.post("/approvals", response_model=ApprovalOut, status_code=status.HTTP_201_CREATED)
def request_approval(
    body: ApprovalRequest, principal: OwnerOrCounter, db: DbSession
) -> ApprovalOut:
    """The owner types their PIN at the counter. The approval is good for one bill, ten minutes."""
    return approval_service.grant(db, principal.user_id, body)


@router.post("/auth/pin", status_code=status.HTTP_204_NO_CONTENT)
def set_pin(body: PinSet, owner: OwnerOnly, db: DbSession) -> Response:
    """The owner sets or changes their approval PIN (needs their password)."""
    approval_service.set_pin(db, get_user(db, owner.user_id), body.current_password, body.pin)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
