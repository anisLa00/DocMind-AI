import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_session
from src.models.user import User
from src.schemas.common import MessageResponse
from src.schemas.users import ChangePasswordModel, CreateUserModel, UpdateUserModel, UserModel
from src.services.users import UserService
from src.utils.dependencies import get_current_admin, get_current_user

user_router = APIRouter(prefix="/users", tags=["Users"])


def _require_self_or_admin(current_user: User, user_id: uuid.UUID) -> None:
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only manage your own account",
        )


@user_router.post("/", response_model=UserModel, status_code=status.HTTP_201_CREATED)
async def create_user(data: CreateUserModel, session: AsyncSession = Depends(get_session)):
    """Sign up. The only endpoint in this router that does not require a token."""
    return await UserService().create_user(data, session)


@user_router.get("/me", response_model=UserModel)
async def get_my_profile(current_user: User = Depends(get_current_user)):
    return current_user


@user_router.patch("/me", response_model=UserModel)
async def update_my_profile(
    user_data: UpdateUserModel,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await UserService().update_user(current_user.id, user_data, session)


@user_router.post("/me/password", response_model=MessageResponse)
async def change_my_password(
    data: ChangePasswordModel,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await UserService().change_password(
        current_user, data.current_password, data.new_password, session
    )
    return {"message": "Password updated"}


@user_router.delete("/me", response_model=UserModel)
async def delete_my_account(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await UserService().delete_user(current_user.id, session)


@user_router.get("/", response_model=list[UserModel])
async def get_all_users(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    return await UserService().get_all_users(session, limit=limit, offset=offset)


@user_router.get("/email/{email}", response_model=UserModel)
async def get_user_by_email(
    email: str,
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    user = await UserService().get_user_by_email(email, session)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@user_router.get("/id/{user_id}", response_model=UserModel)
async def get_user_by_id(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    _require_self_or_admin(current_user, user_id)

    user = await UserService().get_user_by_id(user_id, session)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@user_router.patch("/update/{user_id}", response_model=UserModel)
async def update_user(
    user_id: uuid.UUID,
    user_data: UpdateUserModel,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    _require_self_or_admin(current_user, user_id)
    return await UserService().update_user(user_id, user_data, session)


@user_router.delete("/{user_id}", response_model=UserModel)
async def delete_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    _require_self_or_admin(current_user, user_id)
    return await UserService().delete_user(user_id, session)
