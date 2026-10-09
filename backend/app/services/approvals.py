"""Owner PIN approvals (G18): the counter asks, the owner types a PIN, and one approval is
good for one bill within ten minutes. Everything is logged: who asked, who approved, why."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now_utc
from app.core.errors import AccountLockedError, AuthenticationError, BusinessRuleError
from app.core.security import hash_password, verify_password
from app.core.tenancy import TENANT_ID
from app.models.approvals import Approval
from app.models.audit import AuditLog
from app.models.enums import AuditAction, Role
from app.models.setup import AppUser
from app.schemas.approvals import ApprovalOut, ApprovalRequest
from app.services.audit import record_event

APPROVAL_MINUTES = 10
MAX_BAD_PINS = 5
LOCK_MINUTES = 15


def set_pin(db: Session, user: AppUser, current_password: str, pin: str) -> None:
    if user.role is not Role.OWNER:
        raise BusinessRuleError("Only an owner has an approval PIN", code="NOT_AN_OWNER")
    if not verify_password(current_password, user.password_hash):
        raise AuthenticationError("Current password is wrong", field="current_password")
    user.pin_hash = hash_password(pin)
    record_event(db, AuditAction.UPDATE, "app_user", user.id, {"pin": "changed"})
    db.commit()


def _recent_failures(db: Session, user_id: int) -> int:
    since = now_utc() - timedelta(minutes=LOCK_MINUTES)
    return db.execute(
        select(func.count())
        .select_from(AuditLog)
        .where(
            AuditLog.tenant_id == TENANT_ID,
            AuditLog.entity == "approval",
            AuditLog.action == AuditAction.LOGIN_FAILED,
            AuditLog.user_id == user_id,
            AuditLog.at >= since,
        )
    ).scalar_one()


def grant(db: Session, requester_id: int, data: ApprovalRequest) -> ApprovalOut:
    if _recent_failures(db, requester_id) >= MAX_BAD_PINS:
        raise AccountLockedError("Too many wrong PINs. Wait 15 minutes or ask the owner to bill.")
    owners = list(
        db.execute(
            select(AppUser).where(
                AppUser.tenant_id == TENANT_ID,
                AppUser.role == Role.OWNER,
                AppUser.is_active.is_(True),
                AppUser.pin_hash.is_not(None),
            )
        ).scalars()
    )
    approver = next(
        (o for o in owners if o.pin_hash and verify_password(data.pin, o.pin_hash)), None
    )
    if approver is None:
        record_event(
            db,
            AuditAction.LOGIN_FAILED,
            "approval",
            None,
            {"action": data.action.value},
            user_id=requester_id,
        )
        db.commit()
        raise AuthenticationError(
            "That PIN is not right." if owners else "No owner has set an approval PIN yet.",
            field="pin",
        )
    approval = Approval(
        tenant_id=TENANT_ID,
        action=data.action,
        party_id=data.party_id,
        reason=data.reason,
        requested_by=requester_id,
        approved_by=approver.id,
        expires_at=now_utc() + timedelta(minutes=APPROVAL_MINUTES),
    )
    db.add(approval)
    db.flush()
    record_event(
        db,
        AuditAction.OVERRIDE,
        "approval",
        approval.id,
        {
            "action": data.action.value,
            "reason": data.reason,
            "party_id": data.party_id,
            "approved_by": approver.id,
        },
        user_id=requester_id,
    )
    db.commit()
    return ApprovalOut(
        id=approval.id,
        action=approval.action,
        expires_at=approval.expires_at,
        approved_by_name=approver.full_name,
    )


def load_valid(db: Session, ids: list[int], requester_id: int, party_id: int) -> list[Approval]:
    """Approvals this user may use now, for this customer. Unknown, used, expired or someone
    else's approvals are refused rather than ignored."""
    found: list[Approval] = []
    now = datetime.now(UTC)
    for approval_id in ids:
        row = db.get(Approval, approval_id)
        ok = (
            row is not None
            and row.tenant_id == TENANT_ID
            and row.used_at is None
            and row.expires_at > now
            and row.requested_by == requester_id
            and (row.party_id is None or row.party_id == party_id)
        )
        if not ok or row is None:
            raise BusinessRuleError(
                "That owner approval has expired or was already used. Ask the owner again.",
                code="APPROVAL_INVALID",
                requires_owner_approval=True,
            )
        found.append(row)
    return found


def mark_used(approvals: list[Approval], ref: str) -> None:
    now = datetime.now(UTC)
    for row in approvals:
        row.used_at = now
        row.used_ref = ref
