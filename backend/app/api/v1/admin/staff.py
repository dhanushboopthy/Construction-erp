"""Duolink staff accounts (Milestone 17, ADR 0013). Support may read the list; a Super Admin
makes every change."""

from fastapi import APIRouter, status

from app.api.deps import DbSession, PlatformAdminUser, SuperAdminOnly
from app.schemas.platform import StaffCreate, StaffRow, StaffUpdate, TemporaryPassword
from app.services.platform import staff as service

router = APIRouter(prefix="/staff", tags=["admin"])


@router.get("", response_model=list[StaffRow])
def list_staff(_: PlatformAdminUser, db: DbSession) -> list[StaffRow]:
    return service.list_staff(db)


@router.post("", response_model=StaffRow, status_code=status.HTTP_201_CREATED)
def create_staff(body: StaffCreate, admin: SuperAdminOnly, db: DbSession) -> StaffRow:
    """The password is temporary: the new member must change it at their first sign-in."""
    return service.create_staff(db, body, admin.admin_id)


@router.patch("/{staff_id}", response_model=StaffRow)
def update_staff(
    staff_id: int, body: StaffUpdate, admin: SuperAdminOnly, db: DbSession
) -> StaffRow:
    """Name, mobile, role, active. Nobody lowers their own access, and the last active Super
    Admin stays one (409 LAST_SUPER_ADMIN, SELF_CHANGE)."""
    return service.update_staff(db, staff_id, body, admin.admin_id)


@router.post("/{staff_id}/reset-password", response_model=TemporaryPassword)
def reset_password(staff_id: int, admin: SuperAdminOnly, db: DbSession) -> TemporaryPassword:
    """A temporary password, shown once. Their sessions end; they must change it to continue."""
    return TemporaryPassword(
        temporary_password=service.reset_password(db, staff_id, admin.admin_id)
    )


@router.post("/{staff_id}/unlock", response_model=StaffRow)
def unlock(staff_id: int, admin: SuperAdminOnly, db: DbSession) -> StaffRow:
    return service.unlock(db, staff_id, admin.admin_id)


@router.post("/{staff_id}/sign-out", response_model=StaffRow)
def sign_out(staff_id: int, admin: SuperAdminOnly, db: DbSession) -> StaffRow:
    return service.sign_out(db, staff_id, admin.admin_id)
