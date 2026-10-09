from fastapi import APIRouter, status

from app.api.deps import DbSession, OwnerOnly
from app.schemas.user import PasswordReset, UserCreate, UserOut, UserUpdate
from app.services import users as user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(_: OwnerOnly, db: DbSession) -> list[UserOut]:
    return [UserOut.model_validate(u) for u in user_service.list_users(db)]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, _: OwnerOnly, db: DbSession) -> UserOut:
    return UserOut.model_validate(user_service.create_user(db, body))


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: int, _: OwnerOnly, db: DbSession) -> UserOut:
    return UserOut.model_validate(user_service.get_user(db, user_id))


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, owner: OwnerOnly, db: DbSession) -> UserOut:
    return UserOut.model_validate(user_service.update_user(db, user_id, body, owner.user_id))


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(user_id: int, body: PasswordReset, _: OwnerOnly, db: DbSession) -> None:
    user_service.reset_password(db, user_id, body.new_password)
