from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime,timezone

from src.db.database import get_session
from src.schemas.auth import LoginUserModel,LoginResponseModel,LogoutModel
from src.services.auth import AuthService
from src.models.user import User
from src.utils.dependencies import get_current_user,RefreshTokenBearer,AccessTokenBearer
from src.schemas.users import UserModel
from src.utils.jwt import create_access_token
from src.utils.redis import revoke_token
from src.utils.dependencies import RefreshTokenBearer,revoke_token_data,decode_token




auth_router = APIRouter(
    prefix="/auth",
    tags=["auth"]
)


@auth_router.post("/login",response_model=LoginResponseModel)
async def login_user(login_data: LoginUserModel,session: AsyncSession = Depends(get_session)):
    result = await AuthService().login_user(login_data,session)
    if result is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    return result


@auth_router.get("/me",response_model=UserModel)
async def get_me(current_user:User=Depends(get_current_user)):
    return current_user

@auth_router.post("/refresh")
async def refresh_access_token(
    token_data: dict = Depends(RefreshTokenBearer())
):
    user_id = token_data["user"]

    new_access_token = create_access_token(
        user_id=user_id
    )

    return {
        "access_token": new_access_token,
        "token_type": "bearer"
    }

@auth_router.post("/logout")
async def logout(data: LogoutModel):
    refresh_data = decode_token(data.refresh_token)

    await revoke_token_data(refresh_data)

    if data.access_token:
        try:
            access_data = decode_token(data.access_token)
            await revoke_token_data(access_data)
        except HTTPException:
            pass

    return {"message": "Logged out"}