from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_session
from src.schemas.users import CreateUserModel, UserModel,UpdateUserModel
from src.services.users import UserService
import uuid



user_router = APIRouter(
    prefix="/users",
    tags=["Users"]
)


@user_router.post("/", response_model=UserModel)
async def create_user(
    data: CreateUserModel,
    session: AsyncSession = Depends(get_session)
):
    return await UserService().create_user(data,session)

@user_router.get("/email/{email}", response_model=UserModel) 
async def get_user_by_email(email:str,session:AsyncSession = Depends(get_session)):

    return await UserService().get_user_by_email(email,session)

@user_router.get("/",response_model=list[UserModel])
async def get_all_user(session:AsyncSession = Depends(get_session)):

    return await UserService().get_all_user(session)

@user_router.get("/id/{user_id}",response_model=UserModel)
async def get_user_by_id(user_id:uuid.UUID,session:AsyncSession=Depends(get_session)):
    return await UserService().get_user_by_id(user_id,session)

@user_router.patch("/update/{user_id}",response_model=UserModel)
async def update_user(user_id:uuid.UUID,user_data:UpdateUserModel,session:AsyncSession=Depends(get_session)):
    return await UserService().update_user(user_id,user_data,session)


@user_router.delete("/{user_id}", response_model=UserModel)
async def delete_user(user_id: uuid.UUID,session: AsyncSession = Depends(get_session)):
    return await UserService().delete_user(user_id, session)

