import contextlib

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_session
from src.models.user import User
from src.schemas.auth import (
    AccessTokenResponse,
    LoginResponseModel,
    LoginUserModel,
    LogoutModel,
)
from src.schemas.common import MessageResponse
from src.schemas.users import UserModel
from src.services.auth import AuthService
from src.utils.dependencies import RefreshTokenBearer, get_current_user, revoke_token_data
from src.utils.jwt import create_access_token, decode_token

auth_router = APIRouter(prefix="/auth", tags=["Auth"])


@auth_router.post("/login", response_model=LoginResponseModel)
async def login_user(login_data: LoginUserModel, session: AsyncSession = Depends(get_session)):
    tokens = await AuthService().login_user(login_data, session)
    if tokens is None:
        # One message for every failure mode, so this cannot enumerate accounts.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return tokens


@auth_router.get("/me", response_model=UserModel)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@auth_router.post("/refresh", response_model=AccessTokenResponse)
async def refresh_access_token(token_data: dict = Depends(RefreshTokenBearer())):
    return {
        "access_token": create_access_token(user_id=str(token_data["user"])),
        "token_type": "bearer",
    }


@auth_router.post("/logout", response_model=MessageResponse)
async def logout(data: LogoutModel):
    """Revoke a refresh token, and the access token issued alongside it."""
    await revoke_token_data(decode_token(data.refresh_token))

    if data.access_token:
        # An already-expired access token needs no revocation.
        with contextlib.suppress(HTTPException):
            await revoke_token_data(decode_token(data.access_token))

    return {"message": "Logged out"}
