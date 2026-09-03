from sqlalchemy.ext.asyncio import AsyncSession
from src.schemas.auth import LoginUserModel
from .users import UserService
from pwdlib import PasswordHash
from src.utils.jwt import create_access_token


password_hash = PasswordHash.recommended()
class AuthService:

    async def login_user(self,login_data: LoginUserModel,session: AsyncSession):
        user = await UserService().get_user_by_email(
            login_data.email,
            session
        )
        if not user:
           return None

        if not password_hash.verify(login_data.password,user.password_hash):
           return None
        
        access_token = create_access_token(
        user_id=str(user.id)
)
        refresh_token=create_access_token(
            user_id=str(user.id),
            refresh=True
        )

        return {
           "access_token": access_token,
           "refresh_token":refresh_token,
           "token_type": "bearer"
}